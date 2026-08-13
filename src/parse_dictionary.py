"""Parse the official CFIHOS v2.0 XLSX dictionary into the canonical model YAML."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path
from typing import Any
from xml.etree import ElementTree
from zipfile import ZipFile

import yaml

SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"m": SHEET_NS, "r": REL_NS}

SUBJECT_AREAS = {
    "A.2": "functional_asset",
    "A.3": "physical_asset",
    "A.4": "classification",
    "A.5": "property",
    "A.6": "document_reference",
    "A.7": "document_master",
    "A.8": "document_control",
    "A.9": "spare_part",
}

SPINE_ENTITIES = (
    "plant",
    "process_unit",
    "tag",
    "equipment",
    "document_master",
    "tag_or_equipment_class",
    "tag_class",
    "equipment_class",
    "tag_class_equipment_class_relationship",
    "property",
    "tag_or_equipment_class_property",
    "tag_class_property",
    "equipment_class_property",
    "tag_property",
    "equipment_property",
)

TECHNICAL_COLUMNS = (
    {
        "name": "spine_id",
        "datatype": "STRING",
        "nullable": False,
        "definition": "Golden identifier assigned by the consolidation hub.",
    },
    {
        "name": "valid_from",
        "datatype": "TIMESTAMP",
        "nullable": False,
        "definition": "Start of validity for this published version.",
    },
    {
        "name": "valid_to",
        "datatype": "TIMESTAMP",
        "nullable": True,
        "definition": "End of validity for this published version; null means current.",
    },
    {
        "name": "is_current",
        "datatype": "BOOLEAN",
        "nullable": False,
        "definition": "Whether this is the current published version.",
    },
    {
        "name": "recorded_at",
        "datatype": "TIMESTAMP",
        "nullable": False,
        "definition": "Time this version was recorded by the consolidation hub.",
    },
)


def slug(value: str) -> str:
    """Convert a CFIHOS label to a stable SQL/Python identifier."""
    value = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    return value.strip("_")


def sql_type(source_format: str) -> str:
    """Map only explicit dictionary formats to broad Databricks SQL types."""
    source_format = source_format.strip()
    if re.fullmatch(r"Text, max \d+ characters", source_format):
        return "STRING"
    mapping = {
        "Integer": "BIGINT",
        "Boolean (Yes/No)": "BOOLEAN",
        "Date": "DATE",
        # The dictionary does not specify scale for either numeric format. DOUBLE
        # preserves the declared numeric category without inventing a scale.
        "NUM": "DOUBLE",
        "Decimal (10)": "DOUBLE",
    }
    if source_format not in mapping:
        raise ValueError(f"unsupported dictionary format: {source_format!r}")
    return mapping[source_format]


def _cell_value(cell: ElementTree.Element, shared_strings: list[str]) -> str:
    value = cell.find(f"{{{SHEET_NS}}}v")
    raw = "" if value is None or value.text is None else value.text
    if cell.attrib.get("t") == "s" and raw:
        return shared_strings[int(raw)]
    if cell.attrib.get("t") == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{{{SHEET_NS}}}t"))
    return raw


def read_xlsx(path: Path) -> dict[str, list[tuple[int, dict[str, str]]]]:
    """Read string-valued XLSX worksheets with the standard library."""
    with ZipFile(path) as archive:
        shared_root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
        shared_strings = [
            "".join(node.text or "" for node in item.iter(f"{{{SHEET_NS}}}t"))
            for item in shared_root.findall(f"{{{SHEET_NS}}}si")
        ]
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        rels = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {
            rel.attrib["Id"]: rel.attrib["Target"].lstrip("/")
            for rel in rels.findall(f"{{{PACKAGE_REL_NS}}}Relationship")
        }
        sheets: dict[str, list[tuple[int, dict[str, str]]]] = {}
        for sheet in workbook.findall("m:sheets/m:sheet", NS):
            rel_id = sheet.attrib[f"{{{REL_NS}}}id"]
            target = targets[rel_id]
            if not target.startswith("xl/"):
                target = f"xl/{target}"
            root = ElementTree.fromstring(archive.read(target))
            raw_rows: list[tuple[int, dict[str, str]]] = []
            for row in root.findall("m:sheetData/m:row", NS):
                values: dict[str, str] = {}
                for cell in row.findall("m:c", NS):
                    column = re.match(r"[A-Z]+", cell.attrib["r"])
                    assert column is not None
                    values[column.group()] = _cell_value(cell, shared_strings)
                raw_rows.append((int(row.attrib["r"]), values))
            if not raw_rows:
                sheets[sheet.attrib["name"]] = []
                continue
            _, header_cells = raw_rows[0]
            headers = {column: value.strip() for column, value in header_cells.items()}
            sheets[sheet.attrib["name"]] = [
                (number, {headers[col]: value for col, value in cells.items() if col in headers})
                for number, cells in raw_rows[1:]
            ]
        return sheets


def _exception(sheet: str, row: int, reason: str, values: dict[str, str]) -> dict[str, Any]:
    return {"sheet": sheet, "row": row, "reason": reason, "values": values}


def parse_dictionary(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return the canonical model and every row that could not be interpreted."""
    sheets = read_xlsx(path)
    exceptions: list[dict[str, Any]] = []
    entities: dict[str, dict[str, Any]] = {}

    if "Data Dictionary" not in sheets or "Relationships" not in sheets:
        raise ValueError("workbook must contain Data Dictionary and Relationships sheets")

    for row_number, row in sheets["Data Dictionary"]:
        kind = row.get("Object", "").strip()
        source_entity = row.get("Entity Filter", "").strip()
        name = row.get("Name", "").strip()
        try:
            if kind == "Entity :":
                section = row.get("Section", "").strip()
                area_key = section[:3]
                if area_key not in SUBJECT_AREAS:
                    raise ValueError(f"unknown subject area for section {section!r}")
                if not name or source_entity != name:
                    raise ValueError("entity name and filter must be equal and non-empty")
                entity_slug = slug(name)
                if entity_slug in entities:
                    raise ValueError(f"duplicate entity {name!r}")
                entities[entity_slug] = {
                    "name": entity_slug,
                    "source_name": name,
                    "cfihos_code": row.get("CFIHOS unique code", "").strip(),
                    "section": section,
                    "subject_area": SUBJECT_AREAS[area_key],
                    "definition": row.get("Definition", ""),
                    "note": row.get("Note / comment", ""),
                    "attributes": [],
                }
            elif kind == "Attribute :":
                entity_slug = slug(source_entity)
                if entity_slug not in entities:
                    raise ValueError(f"attribute refers to unknown entity {source_entity!r}")
                source_format = row.get("Format", "").strip()
                requirement = row.get("Identifier / Mandatory / Optional", "").strip()
                if requirement not in {"Identifier", "Mandatory", "Optional"}:
                    raise ValueError(f"unsupported requirement {requirement!r}")
                attribute = {
                    "name": slug(name),
                    "source_name": name,
                    "cfihos_code": row.get("CFIHOS unique code", "").strip(),
                    "definition": row.get("Definition", ""),
                    "note": row.get("Note / comment", ""),
                    "example": row.get("Example", ""),
                    "requirement": requirement.lower(),
                    "source_format": source_format,
                    "datatype": sql_type(source_format),
                    "references": slug(row.get("Constraint : \nMust be present in", "")),
                    "relationship_verb": row.get("Relationship verb", ""),
                }
                existing = {item["name"] for item in entities[entity_slug]["attributes"]}
                if not attribute["name"] or attribute["name"] in existing:
                    raise ValueError(f"blank or duplicate attribute {name!r}")
                entities[entity_slug]["attributes"].append(attribute)
            elif any(value.strip() for value in row.values()):
                raise ValueError(f"unsupported object marker {kind!r}")
        except (KeyError, ValueError) as error:
            exceptions.append(_exception("Data Dictionary", row_number, str(error), row))

    relationships: list[dict[str, Any]] = []
    for row_number, row in sheets["Relationships"]:
        try:
            parent = slug(row.get("Parent entity", ""))
            child = slug(row.get("Child entity", ""))
            if parent not in entities or child not in entities:
                raise ValueError(f"relationship references unknown entities {parent!r}, {child!r}")
            relationship_type = row.get("Type of relationship", "").strip().lower()
            requirement = row.get("The relationship is", "").strip().lower()
            if relationship_type not in {"identifying", "non-identifying"}:
                raise ValueError(f"unsupported relationship type {relationship_type!r}")
            if requirement not in {"mandatory", "optional"}:
                raise ValueError(f"unsupported relationship requirement {requirement!r}")
            relationships.append(
                {
                    "section": row.get("Data Model Section", "").strip(),
                    "parent": parent,
                    "child": child,
                    "parent_to_child_phrase": row.get("Parent to child phrase", ""),
                    "child_to_parent_phrase": row.get("Child to parent phrase (optional)", ""),
                    "relationship_type": relationship_type,
                    "requirement": requirement,
                    "cardinality": {
                        "parent_to_child": row.get(
                            "Parent-to-Child plain English sentence", ""
                        ),
                        "child_to_parent": row.get(
                            "Child-to-Parent plain English sentence", ""
                        ),
                    },
                }
            )
        except ValueError as error:
            exceptions.append(_exception("Relationships", row_number, str(error), row))

    missing_spine = sorted(set(SPINE_ENTITIES) - entities.keys())
    if missing_spine:
        exceptions.append(
            _exception("Data Dictionary", 0, f"missing spine entities: {missing_spine}", {})
        )

    model = {
        "metadata": {
            "name": "CFIHOS v2.0-aligned canonical model",
            "cfihos_version": "2.0",
            "source": path.name,
            "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "license": "CC BY 4.0",
            "publisher": "IOGP JIP36",
        },
        "subject_areas": SUBJECT_AREAS,
        "generation": {
            "spine_entities": list(SPINE_ENTITIES),
            "technical_columns": list(TECHNICAL_COLUMNS),
        },
        "entities": entities,
        "relationships": relationships,
    }
    return model, exceptions


def write_yaml(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(value, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dictionary", type=Path)
    parser.add_argument("--output", type=Path, default=Path("model/model.yml"))
    parser.add_argument(
        "--exceptions", type=Path, default=Path("model/parse_exceptions.yml")
    )
    args = parser.parse_args(argv)
    model, exceptions = parse_dictionary(args.dictionary)
    write_yaml(args.output, model)
    write_yaml(args.exceptions, {"exceptions": exceptions})
    if exceptions:
        print(f"dictionary parse failed with {len(exceptions)} exception(s)", file=sys.stderr)
        return 1
    print(
        f"wrote {args.output}: {len(model['entities'])} entities, "
        f"{sum(len(entity['attributes']) for entity in model['entities'].values())} attributes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
