"""Generate Databricks SQL DDL exclusively from model/model.yml."""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ATTRIBUTION = """-- CFIHOS materials are published by IOGP JIP36 under CC BY 4.0.
-- This generated output is CFIHOS v2.0-aligned; it is not CFIHOS certified.
-- PK/FK constraints are informational. The validation job performs enforcement.
"""

SKIPPED_FOREIGN_KEY_REASONS = (
    "target_out_of_scope",
    "composite_target_key",
    "renamed_key",
    "target_has_no_single_identifier",
)


@dataclass(frozen=True)
class ForeignKey:
    source_entity: str
    source_attribute: str
    target_entity: str
    target_attribute: str
    constraint_name: str

    def render(self, catalog: str, entities: dict[str, dict[str, Any]]) -> str:
        return (
            f"ALTER TABLE {table_name(catalog, entities[self.source_entity])}\n"
            f"ADD CONSTRAINT {quote_identifier(self.constraint_name)} FOREIGN KEY "
            f"({quote_identifier(self.source_attribute)}) REFERENCES "
            f"{table_name(catalog, entities[self.target_entity])} "
            f"({quote_identifier(self.target_attribute)}) NOT ENFORCED;\n"
        )

    def report_entry(self) -> dict[str, str]:
        return {
            "constraint_name": self.constraint_name,
            "source_entity": self.source_entity,
            "source_attribute": self.source_attribute,
            "target_entity": self.target_entity,
            "target_attribute": self.target_attribute,
        }


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


def _foreign_key_decisions(
    entity: dict[str, Any],
    entities: dict[str, dict[str, Any]],
    generated_entities: set[str],
) -> tuple[list[ForeignKey], list[dict[str, str]]]:
    foreign_keys: list[ForeignKey] = []
    skipped: list[dict[str, str]] = []
    for attribute in entity["attributes"]:
        target_name = attribute.get("references")
        if not target_name:
            continue
        relationship = {
            "source_entity": entity["name"],
            "source_attribute": attribute["name"],
            "target_entity": target_name,
        }
        if target_name not in generated_entities:
            skipped.append({**relationship, "reason": "target_out_of_scope"})
            continue
        target = entities[target_name]
        target_pk = [a for a in target["attributes"] if a["requirement"] == "identifier"]
        if not target_pk:
            skipped.append({**relationship, "reason": "target_has_no_single_identifier"})
            continue
        if len(target_pk) > 1:
            skipped.append({**relationship, "reason": "composite_target_key"})
            continue
        if target_pk[0]["name"] != attribute["name"]:
            skipped.append({**relationship, "reason": "renamed_key"})
            continue
        constraint_name = f"fk_{entity['name']}_{attribute['name']}"
        foreign_keys.append(
            ForeignKey(
                source_entity=entity["name"],
                source_attribute=attribute["name"],
                target_entity=target_name,
                target_attribute=target_pk[0]["name"],
                constraint_name=constraint_name,
            )
        )
    return foreign_keys, skipped


def _foreign_keys(
    catalog: str,
    entity: dict[str, Any],
    entities: dict[str, dict[str, Any]],
    generated_entities: set[str],
    *,
    emitted_report: list[ForeignKey] | None = None,
    skipped_report: list[dict[str, str]] | None = None,
) -> list[str]:
    foreign_keys, skipped = _foreign_key_decisions(entity, entities, generated_entities)
    if emitted_report is not None:
        emitted_report.extend(foreign_keys)
    if skipped_report is not None:
        skipped_report.extend(skipped)
    return [foreign_key.render(catalog, entities) for foreign_key in foreign_keys]


def render_entity(
    catalog: str,
    entity: dict[str, Any],
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


def _generation_report(
    model: dict[str, Any], foreign_keys: list[ForeignKey], skipped: list[dict[str, str]]
) -> dict[str, Any]:
    reason_counts = {
        reason: sum(item["reason"] == reason for item in skipped)
        for reason in SKIPPED_FOREIGN_KEY_REASONS
    }
    return {
        "report_version": 1,
        "model": {
            "name": model["metadata"]["name"],
            "cfihos_version": model["metadata"]["cfihos_version"],
            "source": model["metadata"]["source"],
            "source_sha256": model["metadata"]["source_sha256"],
        },
        "generated_entities": list(model["generation"]["spine_entities"]),
        "foreign_keys": {
            "summary": {
                "considered": len(foreign_keys) + len(skipped),
                "emitted": len(foreign_keys),
                "skipped": len(skipped),
                "skipped_by_reason": reason_counts,
            },
            "emitted": [foreign_key.report_entry() for foreign_key in foreign_keys],
            "skipped": skipped,
        },
    }


def _write_yaml(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(value, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )


def generate(
    model: dict[str, Any],
    output_dir: Path,
    catalog: str = "${catalog}",
    report_path: Path = Path("model/generation_report.yml"),
) -> list[Path]:
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
                    model["generation"]["technical_columns"],
                )
            )
        path.write_text("\n".join(contents), encoding="utf-8")
        generated.append(path)

    foreign_keys: list[ForeignKey] = []
    skipped: list[dict[str, str]] = []
    foreign_key_statements: list[str] = []
    for name in spine_names:
        foreign_key_statements.extend(
            _foreign_keys(
                catalog,
                entities[name],
                entities,
                generated_entities,
                emitted_report=foreign_keys,
                skipped_report=skipped,
            )
        )

    foreign_key_path = output_dir / "90_foreign_keys.sql"
    foreign_key_sql = [ATTRIBUTION]
    foreign_key_sql.extend(foreign_key_statements)
    foreign_key_path.write_text("\n".join(foreign_key_sql), encoding="utf-8")
    generated.append(foreign_key_path)
    _write_yaml(report_path, _generation_report(model, foreign_keys, skipped))
    return generated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("src/ddl"))
    parser.add_argument("--report", type=Path, default=Path("model/generation_report.yml"))
    args = parser.parse_args(argv)
    model = yaml.safe_load(args.model.read_text(encoding="utf-8"))
    paths = generate(model, args.output_dir, report_path=args.report)
    print(f"generated {len(paths)} DDL files in {args.output_dir} and {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
