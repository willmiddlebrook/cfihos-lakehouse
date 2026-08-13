"""Generate Databricks SQL DDL exclusively from model/model.yml."""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

ATTRIBUTION = """-- CFIHOS materials are published by IOGP JIP36 under CC BY 4.0.
-- This generated output is CFIHOS v2.0-aligned; it is not CFIHOS certified.
-- PK/FK constraints below are informational. The validation job performs enforcement.
"""


def quote_identifier(value: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", value):
        raise ValueError(f"unsafe generated identifier: {value!r}")
    return f"`{value}`"


def quote_comment(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def schema_name(subject_area: str) -> str:
    return f"cfihos_{subject_area}"


def table_name(catalog: str, entity: dict[str, Any]) -> str:
    return ".".join(
        [
            catalog,
            quote_identifier(schema_name(entity["subject_area"])),
            quote_identifier(entity["name"]),
        ]
    )


def _foreign_keys(
    catalog: str,
    entity: dict[str, Any],
    entities: dict[str, dict[str, Any]],
    generated_entities: set[str],
) -> list[str]:
    constraints = []
    for attribute in entity["attributes"]:
        target_name = attribute.get("references")
        if not target_name or target_name not in generated_entities:
            continue
        target = entities[target_name]
        target_pk = [a for a in target["attributes"] if a["requirement"] == "identifier"]
        if len(target_pk) != 1 or target_pk[0]["name"] != attribute["name"]:
            continue
        constraint_name = f"fk_{entity['name']}_{attribute['name']}"
        constraints.append(
            f"  CONSTRAINT {quote_identifier(constraint_name)} FOREIGN KEY "
            f"({quote_identifier(attribute['name'])}) REFERENCES "
            f"{table_name(catalog, target)} ({quote_identifier(target_pk[0]['name'])}) "
            "NOT ENFORCED"
        )
    return constraints


def render_entity(
    catalog: str,
    entity: dict[str, Any],
    entities: dict[str, dict[str, Any]],
    generated_entities: set[str],
    technical_columns: list[dict[str, Any]],
) -> str:
    columns = []
    standard_names = {item["name"] for item in entity["attributes"]}
    for attribute in entity["attributes"]:
        required = attribute["requirement"] in {"identifier", "mandatory"}
        nullability = " NOT NULL" if required else ""
        columns.append(
            f"  {quote_identifier(attribute['name'])} {attribute['datatype']}{nullability} "
            f"COMMENT {quote_comment(attribute['definition'])}"
        )
    for column in technical_columns:
        if column["name"] in standard_names:
            raise ValueError(f"technical column collides with dictionary: {column['name']}")
        nullability = "" if column["nullable"] else " NOT NULL"
        columns.append(
            f"  {quote_identifier(column['name'])} {column['datatype']}{nullability} "
            f"COMMENT {quote_comment('[Implementation] ' + column['definition'])}"
        )

    primary_key = [
        quote_identifier(attribute["name"])
        for attribute in entity["attributes"]
        if attribute["requirement"] == "identifier"
    ]
    constraints = []
    if primary_key:
        constraints.append(
            f"  CONSTRAINT {quote_identifier('pk_' + entity['name'])} PRIMARY KEY "
            f"({', '.join(primary_key)}) NOT ENFORCED"
        )
    constraints.extend(_foreign_keys(catalog, entity, entities, generated_entities))
    body = ",\n".join(columns + constraints)
    comment = (
        f"{entity['definition']} CFIHOS v2.0-aligned. "
        "Declared constraints are informational; validation jobs perform enforcement."
    )
    return (
        f"CREATE TABLE IF NOT EXISTS {table_name(catalog, entity)} (\n{body}\n)\n"
        f"COMMENT {quote_comment(comment)}\n"
        "TBLPROPERTIES (\n"
        "  'cfihos_version' = '2.0',\n"
        "  'delta.enableChangeDataFeed' = 'true',\n"
        "  'constraints_enforced' = 'false'\n"
        ");\n"
    )


def generate(model: dict[str, Any], output_dir: Path, catalog: str = "${catalog}") -> list[Path]:
    entities = model["entities"]
    spine_names = model["generation"]["spine_entities"]
    generated_entities = set(spine_names)
    missing = sorted(set(spine_names) - entities.keys())
    if missing:
        raise ValueError(f"model generation profile references missing entities: {missing}")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for name in spine_names:
        grouped[entities[name]["subject_area"]].append(entities[name])
    output_dir.mkdir(parents=True, exist_ok=True)
    generated = []
    for sequence, area in enumerate(sorted(grouped), start=1):
        path = output_dir / f"{sequence:02d}_{area}.sql"
        contents = [ATTRIBUTION]
        schema_comment = f"CFIHOS v2.0-aligned {area.replace('_', ' ')} subject area."
        contents.append(
            f"CREATE SCHEMA IF NOT EXISTS {catalog}.{quote_identifier(schema_name(area))} "
            f"COMMENT {quote_comment(schema_comment)} ;\n"
        )
        for entity in grouped[area]:
            contents.append(
                render_entity(
                    catalog,
                    entity,
                    entities,
                    generated_entities,
                    model["generation"]["technical_columns"],
                )
            )
        path.write_text("\n".join(contents), encoding="utf-8")
        generated.append(path)
    return generated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("src/ddl"))
    args = parser.parse_args(argv)
    model = yaml.safe_load(args.model.read_text(encoding="utf-8"))
    paths = generate(model, args.output_dir)
    print(f"generated {len(paths)} subject-area DDL files in {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
