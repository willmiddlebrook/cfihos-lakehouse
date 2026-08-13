"""Offline producer/consumer checks for configured value-map targets."""

from __future__ import annotations

import csv
import io
import sys
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

try:
    from src.load_rdl import decode_csv, rdl_table_name, sql_name
except ModuleNotFoundError:  # Serverless Python-file tasks put src/ on sys.path.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from load_rdl import decode_csv, rdl_table_name, sql_name


@dataclass(frozen=True)
class TargetWarning:
    """A value-map target set that cannot be checked against a supplied Core RDL."""

    key: str
    reason: str
    reference_entity: str | None
    reference_table: str | None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "key": self.key,
            "status": "unverifiable",
            "reason": self.reason,
            "reference_entity": self.reference_entity,
            "reference_table": self.reference_table,
        }


@dataclass(frozen=True)
class ConfigContractResult:
    """Errors block a config; warnings require a proposal acknowledgement."""

    errors: tuple[str, ...]
    warnings: tuple[TargetWarning, ...]


@cache
def _rdl_files_by_table(spec_dir_text: str) -> dict[str, Path]:
    spec_dir = Path(spec_dir_text)
    files: dict[str, Path] = {}
    for path in sorted(spec_dir.glob("*.csv")):
        table = rdl_table_name(path)
        if table in files:
            raise ValueError(f"multiple Core RDL files resolve to cfihos_ref.{table}")
        files[table] = path
    return files


@cache
def _identifier_values(path_text: str, identifier: str) -> frozenset[str]:
    path = Path(path_text)
    text, _ = decode_csv(path)
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        source_header = next(reader)
    except (StopIteration, csv.Error) as error:
        raise ValueError(f"{path.name}: header parse failed: {error}") from error
    while source_header and not source_header[-1].strip():
        source_header.pop()
    columns = [sql_name(value) for value in source_header]
    if identifier not in columns:
        raise ValueError(
            f"cfihos_ref.{rdl_table_name(path)} has no identifier column {identifier}"
        )
    position = columns.index(identifier)
    values: set[str] = set()
    try:
        for row in reader:
            while len(row) > len(columns) and not row[-1].strip():
                row.pop()
            if len(row) != len(columns):
                raise ValueError(
                    f"{path.name}:{reader.line_num}: expected {len(columns)} fields, "
                    f"found {len(row)}"
                )
            values.add(row[position].strip())
    except csv.Error as error:
        raise ValueError(f"{path.name}:{reader.line_num}: CSV parse failed: {error}") from error
    return frozenset(values)


def _attribute(
    model: dict[str, Any], entity_name: str, attribute_name: str
) -> dict[str, Any] | None:
    entity = model.get("entities", {}).get(entity_name)
    if not isinstance(entity, dict):
        return None
    return next(
        (
            item
            for item in entity.get("attributes", [])
            if isinstance(item, dict) and item.get("name") == attribute_name
        ),
        None,
    )


def _single_identifier(model: dict[str, Any], entity_name: str) -> str | None:
    entity = model.get("entities", {}).get(entity_name)
    if not isinstance(entity, dict):
        return None
    identifiers = [
        item.get("name")
        for item in entity.get("attributes", [])
        if isinstance(item, dict) and item.get("requirement") == "identifier"
    ]
    return identifiers[0] if len(identifiers) == 1 and isinstance(identifiers[0], str) else None


def validate_value_map_targets(
    config: dict[str, Any], model: dict[str, Any], spec_dir: Path
) -> ConfigContractResult:
    """Verify each configured target against Core RDL or return an acknowledgement warning.

    The check is deliberately offline. Core RDL identifier columns are parsed once per
    process and cached by file and identifier.
    """

    errors: list[str] = []
    warnings: list[TargetWarning] = []
    value_maps = config.get("value_maps", {})
    if not isinstance(value_maps, dict):
        return ConfigContractResult((), ())
    try:
        rdl_files = _rdl_files_by_table(str(spec_dir.resolve()))
    except ValueError as error:
        return ConfigContractResult((str(error),), ())

    for key, mapping in value_maps.items():
        if not isinstance(key, str) or "." not in key:
            continue
        entity_name, attribute_name = key.split(".", 1)
        attribute = _attribute(model, entity_name, attribute_name)
        if attribute is None:
            continue  # The base config contract reports unknown attributes.
        reference = attribute.get("references")
        reference = reference.strip() if isinstance(reference, str) else ""
        if not reference:
            warnings.append(
                TargetWarning(
                    key,
                    "attribute_has_no_reference",
                    None,
                    None,
                )
            )
            continue
        rdl_path = rdl_files.get(reference)
        if rdl_path is None:
            warnings.append(
                TargetWarning(
                    key,
                    "reference_has_no_core_rdl",
                    reference,
                    None,
                )
            )
            continue
        reference_table = f"cfihos_ref.{reference}"
        identifier = _single_identifier(model, reference)
        if identifier is None:
            warnings.append(
                TargetWarning(
                    key,
                    "reference_has_no_single_identifier",
                    reference,
                    reference_table,
                )
            )
            continue
        try:
            allowed = _identifier_values(str(rdl_path.resolve()), identifier)
        except ValueError as error:
            errors.append(f"value map {key}: {error}")
            continue
        if not isinstance(mapping, dict):
            continue  # The base config contract reports malformed mappings.
        for target in mapping.values():
            normalized_target = "" if target is None else str(target).strip()
            if normalized_target not in allowed:
                errors.append(
                    f"value map {key}: target {target!r} is not present in "
                    f"{reference_table} (identifier {identifier})"
                )

    return ConfigContractResult(tuple(errors), tuple(warnings))
