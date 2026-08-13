"""Conform one source table to the generated CFIHOS model or quarantine each row."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from functools import reduce
from pathlib import Path
from typing import Any

import yaml

try:
    from src.deploy_foundation import split_sql_statements
    from src.identifiers import validate_identifier
    from src.load_rdl import rdl_table_name
except ModuleNotFoundError:  # Serverless Python-file tasks put src/ on sys.path.
    from deploy_foundation import split_sql_statements
    from identifiers import validate_identifier
    from load_rdl import rdl_table_name

_SCRIPT_PATH = Path(globals().get("__file__", sys.argv[0])).resolve()

_DEFAULT_MODEL_FILE = _SCRIPT_PATH.parents[1] / "model" / "model.yml"
_QUARANTINE_DDL = _SCRIPT_PATH.parent / "quarantine.sql"
_RDL_DIR = _SCRIPT_PATH.parents[1] / "spec" / "rdl"
_ALLOWED_CONFIG_KEYS = frozenset(
    {"source", "into", "from", "key", "mode", "territory", "fields", "value_maps"}
)
_REQUIRED_CONFIG_KEYS = frozenset({"source", "into", "from", "key", "fields"})
_ALLOWED_MODES = frozenset({"upsert", "enrich"})
_ALLOWED_DATATYPES = frozenset({"STRING", "BOOLEAN", "DATE", "BIGINT", "DOUBLE", "TIMESTAMP"})
_CATALOG_TOKEN = "${catalog}"
_BIGINT_MIN = -(2**63)
_BIGINT_MAX = 2**63 - 1


class _UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that refuses duplicate keys instead of overwriting them."""


def _construct_unique_mapping(
    loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in result
        except TypeError as error:
            raise ValueError("YAML mapping keys must be scalar values") from error
        if duplicate:
            raise ValueError(f"duplicate YAML key: {key!r}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def _repository_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else _SCRIPT_PATH.parents[1] / path


def expected_rdl_tables(spec_dir: str | Path = _RDL_DIR) -> frozenset[str]:
    """Return the authoritative Core RDL table manifest shipped with the kit."""
    paths = tuple(sorted(Path(spec_dir).glob("*.csv")))
    if not paths:
        raise FileNotFoundError(f"no Core RDL CSVs found in {spec_dir}")
    return frozenset(rdl_table_name(path) for path in paths)


@dataclass(frozen=True)
class AttributeMetadata:
    """The generated rules for one canonical attribute."""

    name: str
    datatype: str
    requirement: str
    reference: str | None

    @property
    def required(self) -> bool:
        return self.requirement in {"identifier", "mandatory"}


@dataclass(frozen=True)
class ParentMetadata:
    """A relationship whose parent key can be checked without inventing a mapping."""

    attribute: str
    entity: str
    key: tuple[str, ...]
    child_key: tuple[str, ...]


@dataclass(frozen=True)
class TechnicalColumn:
    """A generated implementation column that source YAML is not allowed to map."""

    name: str
    datatype: str
    nullable: bool


@dataclass(frozen=True)
class EntityMetadata:
    """Model-driven metadata needed to check and write one entity."""

    name: str
    subject_area: str
    attributes: tuple[AttributeMetadata, ...]
    identifiers: tuple[str, ...]
    parents: tuple[ParentMetadata, ...]
    technical_columns: tuple[TechnicalColumn, ...]

    def attribute(self, name: str) -> AttributeMetadata:
        for item in self.attributes:
            if item.name == name:
                return item
        raise KeyError(name)


@dataclass(frozen=True)
class SourceConfig:
    """A validated one-page source contract."""

    source: str
    into: str
    from_table: str
    key: tuple[str, ...]
    mode: str
    territory: str | None
    fields: dict[str, str]
    value_maps: dict[str, dict[str, str]]


@dataclass(frozen=True)
class RowCheckResult:
    """The canonical values and all reasons produced by a pure row check."""

    values: dict[str, Any]
    reasons: tuple[str, ...]


def _load_yaml(path: Path) -> Any:
    try:
        return yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except (OSError, yaml.YAMLError, ValueError) as error:
        raise ValueError(f"cannot read valid YAML from {path}: {error}") from error


def load_model(model_file: str | Path = _DEFAULT_MODEL_FILE) -> dict[str, Any]:
    """Load the committed generated model."""
    path = _repository_path(model_file)
    payload = _load_yaml(path)
    if not isinstance(payload, dict) or not isinstance(payload.get("entities"), dict):
        raise ValueError(f"{path} does not contain an entities mapping")
    return payload


def entity_metadata(model: Mapping[str, Any], entity: str) -> EntityMetadata:
    """Build required, datatype, reference, and direct-parent rules from model.yml."""
    validate_identifier(entity)
    entities = model.get("entities")
    if not isinstance(entities, Mapping) or entity not in entities:
        raise ValueError(f"unknown CFIHOS entity: {entity}")
    raw_entity = entities[entity]
    if not isinstance(raw_entity, Mapping):
        raise ValueError(f"model metadata for {entity} is not a mapping")
    raw_attributes = raw_entity.get("attributes")
    if not isinstance(raw_attributes, list):
        raise ValueError(f"model metadata for {entity} has no attributes list")

    attributes: list[AttributeMetadata] = []
    for raw in raw_attributes:
        if not isinstance(raw, Mapping):
            raise ValueError(f"model metadata for {entity} contains an invalid attribute")
        name = validate_identifier(raw.get("name"))
        datatype = raw.get("datatype")
        requirement = raw.get("requirement")
        reference = raw.get("references") or None
        if datatype not in _ALLOWED_DATATYPES:
            raise ValueError(f"unsupported model datatype for {entity}.{name}: {datatype!r}")
        if requirement not in {"identifier", "mandatory", "optional"}:
            raise ValueError(
                f"unsupported model requirement for {entity}.{name}: {requirement!r}"
            )
        if reference is not None:
            validate_identifier(reference)
        attributes.append(AttributeMetadata(name, datatype, requirement, reference))

    attribute_names = {item.name for item in attributes}
    identifiers = tuple(item.name for item in attributes if item.requirement == "identifier")
    generated = set(model.get("generation", {}).get("spine_entities", ()))
    parent_candidates: dict[
        tuple[str, tuple[str, ...], tuple[str, ...]], list[str]
    ] = {}
    for item in attributes:
        if not item.reference or item.reference not in generated:
            continue
        parent_raw = entities.get(item.reference)
        if not isinstance(parent_raw, Mapping):
            continue
        parent_attributes = parent_raw.get("attributes", ())
        parent_key = tuple(
            raw.get("name")
            for raw in parent_attributes
            if isinstance(raw, Mapping) and raw.get("requirement") == "identifier"
        )
        child_key: list[str] = []
        for parent_attribute in parent_key:
            if item.name == parent_attribute or item.name.endswith(
                f"_{parent_attribute}"
            ):
                child_key.append(item.name)
            elif parent_attribute in attribute_names:
                child_key.append(parent_attribute)
            else:
                break
        # Do not invent a renamed composite mapping. Relationships that cannot be
        # derived this way remain explicitly accounted for in generation_report.yml.
        if parent_key and len(child_key) == len(parent_key):
            candidate = (item.reference, parent_key, tuple(child_key))
            parent_candidates.setdefault(candidate, []).append(item.name)
    parents = [
        ParentMetadata(
            next(
                (attribute for attribute in candidates if attribute == child_key[-1]),
                candidates[0],
            ),
            parent_entity,
            parent_key,
            child_key,
        )
        for (
            parent_entity,
            parent_key,
            child_key,
        ), candidates in parent_candidates.items()
    ]

    raw_technical = model.get("generation", {}).get("technical_columns", ())
    technical: list[TechnicalColumn] = []
    for raw in raw_technical:
        if not isinstance(raw, Mapping):
            continue
        name = validate_identifier(raw.get("name"))
        datatype = raw.get("datatype")
        if datatype not in _ALLOWED_DATATYPES:
            raise ValueError(f"unsupported technical datatype for {name}: {datatype!r}")
        technical.append(TechnicalColumn(name, datatype, bool(raw.get("nullable", True))))

    subject_area = validate_identifier(raw_entity.get("subject_area"))
    return EntityMetadata(
        name=entity,
        subject_area=subject_area,
        attributes=tuple(attributes),
        identifiers=identifiers,
        parents=tuple(parents),
        technical_columns=tuple(technical),
    )


def _validate_table_template(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("from must be a three-part table name")
    parts = value.split(".")
    if len(parts) != 3:
        raise ValueError("from must be a three-part table name")
    if parts[0] != _CATALOG_TOKEN:
        validate_identifier(parts[0])
    validate_identifier(parts[1])
    validate_identifier(parts[2])
    return value


def _require_nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def validate_config(payload: Any, model: Mapping[str, Any]) -> SourceConfig:
    """Strictly validate an already-loaded source YAML mapping."""
    if not isinstance(payload, Mapping):
        raise ValueError("source YAML must contain one mapping")
    keys = set(payload)
    unknown = sorted(keys - _ALLOWED_CONFIG_KEYS)
    if unknown:
        raise ValueError(f"unknown top-level source keys: {', '.join(unknown)}")
    missing = sorted(_REQUIRED_CONFIG_KEYS - keys)
    if missing:
        raise ValueError(f"missing required source keys: {', '.join(missing)}")

    source = validate_identifier(payload["source"])
    into = validate_identifier(payload["into"])
    metadata = entity_metadata(model, into)
    from_table = _validate_table_template(payload["from"])
    mode = payload.get("mode", "upsert")
    if mode not in _ALLOWED_MODES:
        raise ValueError("mode must be upsert or enrich")

    territory = payload.get("territory")
    if territory is not None:
        territory = _require_nonempty_string(territory, "territory")
        if "\n" in territory or "\r" in territory:
            raise ValueError("territory must be one line")

    raw_fields = payload["fields"]
    if not isinstance(raw_fields, Mapping) or not raw_fields:
        raise ValueError("fields must be a non-empty mapping")
    known_attributes = {item.name for item in metadata.attributes}
    fields: dict[str, str] = {}
    for canonical, source_column in raw_fields.items():
        canonical = validate_identifier(canonical)
        if canonical not in known_attributes:
            raise ValueError(f"{into}.{canonical} is not a model attribute")
        fields[canonical] = validate_identifier(source_column)

    raw_key = payload["key"]
    if not isinstance(raw_key, list) or not raw_key:
        raise ValueError("key must be a non-empty list of canonical attributes")
    key = tuple(validate_identifier(item) for item in raw_key)
    if len(key) != len(set(key)):
        raise ValueError("key must not contain duplicate attributes")
    unmapped_key = [item for item in key if item not in fields]
    if unmapped_key:
        raise ValueError(f"key attributes are not mapped in fields: {', '.join(unmapped_key)}")

    raw_value_maps = payload.get("value_maps", {})
    if not isinstance(raw_value_maps, Mapping):
        raise ValueError("value_maps must be a mapping")
    value_maps: dict[str, dict[str, str]] = {}
    for attribute, raw_mapping in raw_value_maps.items():
        attribute = validate_identifier(attribute)
        if attribute not in known_attributes:
            raise ValueError(f"{into}.{attribute} is not a model attribute")
        if attribute not in fields:
            raise ValueError(f"value_maps.{attribute} has no corresponding fields mapping")
        if not isinstance(raw_mapping, Mapping) or not raw_mapping:
            raise ValueError(f"value_maps.{attribute} must be a non-empty mapping")
        mapping: dict[str, str] = {}
        for source_value, standard_value in raw_mapping.items():
            source_value = _require_nonempty_string(
                source_value, f"value_maps.{attribute} source code"
            )
            standard_value = _require_nonempty_string(
                standard_value, f"value_maps.{attribute}.{source_value} target value"
            )
            if source_value != source_value.strip() or standard_value != standard_value.strip():
                raise ValueError(f"value_maps.{attribute} values must already be trimmed")
            mapping[source_value] = standard_value
        value_maps[attribute] = mapping

    return SourceConfig(
        source=source,
        into=into,
        from_table=from_table,
        key=key,
        mode=mode,
        territory=territory,
        fields=fields,
        value_maps=value_maps,
    )


def validate_source_config(
    yaml_file: str | Path, model_file: str | Path = _DEFAULT_MODEL_FILE
) -> SourceConfig:
    """Load and strictly validate one source YAML before any source data is read."""
    return validate_config(_load_yaml(_repository_path(yaml_file)), load_model(model_file))


def normalize_value(value: Any) -> Any:
    """Trim strings and turn empty strings into missing values."""
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def cast_value(value: Any, datatype: str) -> Any:
    """Cast one non-empty value using the model datatype, raising on failure."""
    value = normalize_value(value)
    if value is None:
        return None
    if datatype == "STRING":
        return str(value).strip()
    if datatype == "BOOLEAN":
        if isinstance(value, bool):
            return value
        normalized = str(value).strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
        raise ValueError(f"cannot cast {value!r} to BOOLEAN")
    if datatype == "BIGINT":
        if isinstance(value, bool) or not re.fullmatch(r"[+-]?\d+", str(value).strip()):
            raise ValueError(f"cannot cast {value!r} to BIGINT")
        result = int(value)
        if not _BIGINT_MIN <= result <= _BIGINT_MAX:
            raise ValueError(f"cannot cast {value!r} to BIGINT")
        return result
    if datatype == "DOUBLE":
        result = float(value)
        if not math.isfinite(result):
            raise ValueError(f"cannot cast {value!r} to DOUBLE")
        return result
    if datatype == "DATE":
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value).strip())
    if datatype == "TIMESTAMP":
        if isinstance(value, datetime):
            return value
        text = str(value).strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        return datetime.fromisoformat(text)
    raise ValueError(f"unsupported model datatype: {datatype!r}")


def missing_reason(attribute: str) -> str:
    return f"{attribute} is required and missing"


def invalid_reference_reason(value: Any, reference: str) -> str:
    return f"{value} is not a valid {reference.replace('_', ' ')}"


def invalid_cast_reason(value: Any, attribute: str, datatype: str) -> str:
    return f"{value} is not a valid {datatype.lower()} for {attribute}"


def missing_parent_reason(parent: str, attribute: str) -> str:
    return f"no existing {parent.replace('_', ' ')} for {attribute}"


def enrich_missing_reason(entity: str) -> str:
    return f"no existing {entity} to enrich"


def _deduplicate_reasons(reasons: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(reasons))


def check_row(
    row: Mapping[str, Any],
    metadata: EntityMetadata,
    *,
    key: Sequence[str],
    mode: str = "upsert",
    value_maps: Mapping[str, Mapping[str, str]] | None = None,
    rdl_values: Mapping[str, set[Any]] | None = None,
    parent_values: Mapping[str, set[tuple[Any, ...]]] | None = None,
    existing: bool = True,
) -> RowCheckResult:
    """Pure reference implementation of all per-row conformance checks."""
    if mode not in _ALLOWED_MODES:
        raise ValueError("mode must be upsert or enrich")
    value_maps = value_maps or {}
    rdl_values = rdl_values or {}
    parent_values = parent_values or {}
    keys = tuple(key)
    required = set(keys)
    if mode == "upsert":
        required.update(item.name for item in metadata.attributes if item.required)
    else:
        required.update(
            item.name
            for item in metadata.attributes
            if item.required and item.name in row
        )

    values: dict[str, Any] = {}
    reasons: list[str] = []
    for item in metadata.attributes:
        raw = normalize_value(row.get(item.name))
        if item.name in required and raw is None:
            reasons.append(missing_reason(item.name))
        prepared = raw
        mapping = value_maps.get(item.name)
        if raw is not None and mapping is not None:
            prepared = mapping.get(str(raw))
            if prepared is None:
                reasons.append(
                    invalid_reference_reason(raw, item.reference or item.name)
                )
        casted = None
        if prepared is not None:
            try:
                casted = cast_value(prepared, item.datatype)
            except (TypeError, ValueError, OverflowError):
                reasons.append(invalid_cast_reason(prepared, item.name, item.datatype))
        values[item.name] = casted

        allowed = rdl_values.get(item.name)
        if casted is not None and allowed is not None:
            normalized_allowed = {normalize_value(value) for value in allowed}
            if casted not in normalized_allowed:
                reasons.append(
                    invalid_reference_reason(casted, item.reference or item.name)
                )

    for parent in metadata.parents:
        if parent.attribute not in row or values.get(parent.attribute) is None:
            continue
        parent_key = tuple(values.get(attribute) for attribute in parent.child_key)
        if any(value is None for value in parent_key):
            continue
        allowed_parents = parent_values.get(parent.attribute)
        if allowed_parents is not None and parent_key not in allowed_parents:
            reasons.append(missing_parent_reason(parent.entity, parent.attribute))

    if mode == "enrich" and not existing:
        reasons.append(enrich_missing_reason(metadata.name))
    return RowCheckResult(values, _deduplicate_reasons(reasons))


def rdl_value_column(attribute: str, reference: str, columns: Sequence[str]) -> str:
    """Pick the referenced value column without source-specific knowledge."""
    validate_identifier(attribute)
    validate_identifier(reference)
    available = set(columns)
    if attribute in available:
        return attribute
    suffix_matches = [
        column
        for column in columns
        if attribute.endswith(f"_{column}")
        and (column == reference or column.startswith(f"{reference}_"))
        and not column.endswith("_cfihos_unique_code")
    ]
    if suffix_matches:
        return max(suffix_matches, key=len)
    for candidate in (
        reference,
        f"{reference}_name",
        f"{reference}_code",
        f"{reference}_short_code",
    ):
        if candidate in available:
            return candidate
    raise ValueError(
        f"cfihos_ref.{reference} has no value column for model attribute {attribute}"
    )


def _resolve_table(template: str, catalog: str) -> str:
    validate_identifier(catalog)
    parts = template.split(".")
    if parts[0] == _CATALOG_TOKEN:
        parts[0] = catalog
    for part in parts:
        validate_identifier(part)
    return ".".join(parts)


def _target_table(catalog: str, metadata: EntityMetadata) -> str:
    validate_identifier(catalog)
    return f"{catalog}.cfihos_{metadata.subject_area}.{metadata.name}"


def _ensure_quarantine(spark: Any, catalog: str) -> None:
    validate_identifier(catalog)
    rendered = _QUARANTINE_DDL.read_text(encoding="utf-8").replace("${catalog}", catalog)
    for statement in split_sql_statements(rendered):
        spark.sql(statement)


def _normalized_column(column: Any, functions: Any) -> Any:
    text = functions.trim(column.cast("string"))
    return functions.when(functions.length(text) == 0, functions.lit(None)).otherwise(text)


def _prepared_column_name(attribute: str) -> str:
    """Return an internal alias that is also a valid SQL identifier."""
    validate_identifier(attribute)
    return f"cfihos_prepared_{attribute}"


def _spark_cast(column_name: str, datatype: str, functions: Any) -> Any:
    validate_identifier(column_name)
    if datatype not in _ALLOWED_DATATYPES:
        raise ValueError(f"unsupported model datatype: {datatype!r}")
    if datatype == "BOOLEAN":
        lowered = functions.lower(functions.col(column_name))
        return functions.when(lowered.isin("true", "false"), lowered.cast("boolean"))
    return functions.expr(f"try_cast(`{column_name}` AS {datatype})")


def _technical_expression(column: TechnicalColumn, functions: Any) -> Any:
    if column.name == "spine_id":
        return functions.expr("uuid()").cast(column.datatype)
    if column.name in {"valid_from", "recorded_at"}:
        return functions.current_timestamp().cast(column.datatype)
    if column.name == "is_current":
        return functions.lit(True).cast(column.datatype)
    if column.nullable:
        return functions.lit(None).cast(column.datatype)
    raise ValueError(
        f"cannot populate generated non-null technical column {column.name}; "
        "source YAML cannot map implementation columns"
    )


def _append_lookup_checks(
    spark: Any,
    frame: Any,
    checks: list[tuple[Any, Any]],
    catalog: str,
    model: Mapping[str, Any],
    metadata: EntityMetadata,
    config: SourceConfig,
    functions: Any,
) -> tuple[Any, set[str]]:
    rdl_checked: set[str] = set()
    core_rdl_tables = expected_rdl_tables()
    model_version = str(model.get("metadata", {}).get("cfihos_version", ""))
    for item in metadata.attributes:
        if item.name not in config.fields or not item.reference:
            continue
        if item.reference not in core_rdl_tables:
            continue
        rdl_table = f"{catalog}.cfihos_ref.{item.reference}"
        if not spark.catalog.tableExists(rdl_table):
            raise ValueError(
                f"required Core RDL table does not exist: {rdl_table}; run load_rdl first"
            )
        rdl = spark.table(rdl_table)
        value_column = rdl_value_column(item.name, item.reference, rdl.columns)
        if "rdl_version" in rdl.columns and model_version:
            rdl = rdl.where(functions.col("rdl_version") == model_version)
        lookup_value = f"_cfihos_rdl_value_{item.name}"
        lookup_marker = f"_cfihos_rdl_match_{item.name}"
        lookup = (
            rdl.select(
                _normalized_column(rdl[value_column], functions).alias(lookup_value)
            )
            .where(functions.col(lookup_value).isNotNull())
            .distinct()
            .withColumn(lookup_marker, functions.lit(True))
        )
        frame = frame.join(
            lookup,
            frame[item.name] == lookup[lookup_value],
            "left",
        ).drop(lookup_value)
        checks.append(
            (
                functions.col(item.name).isNotNull()
                & functions.col(lookup_marker).isNull(),
                functions.concat(
                    functions.col(item.name).cast("string"),
                    functions.lit(
                        f" is not a valid {item.reference.replace('_', ' ')}"
                    ),
                ),
            )
        )
        rdl_checked.add(item.name)

    generated = set(model.get("generation", {}).get("spine_entities", ()))
    entities = model.get("entities", {})
    for parent in metadata.parents:
        # A supplied Core RDL value is the authoritative parent for vocabulary entities;
        # their generated model tables intentionally start empty.
        if parent.attribute not in config.fields or parent.attribute in rdl_checked:
            continue
        if parent.entity not in generated:
            continue
        parent_raw = entities[parent.entity]
        parent_area = validate_identifier(parent_raw["subject_area"])
        parent_table = f"{catalog}.cfihos_{parent_area}.{parent.entity}"
        if not spark.catalog.tableExists(parent_table):
            raise ValueError(f"generated parent table does not exist: {parent_table}")
        lookup = spark.table(parent_table)
        if "is_current" in lookup.columns:
            lookup = lookup.where(functions.col("is_current"))
        aliases = {
            key: f"_cfihos_parent_{parent.attribute}_{key}" for key in parent.key
        }
        marker = f"_cfihos_parent_match_{parent.attribute}"
        lookup = (
            lookup.select(*(lookup[key].alias(alias) for key, alias in aliases.items()))
            .distinct()
            .withColumn(marker, functions.lit(True))
        )
        join_condition = reduce(
            lambda left, right: left & right,
            (
                frame[child] == lookup[aliases[parent_key]]
                for child, parent_key in zip(
                    parent.child_key, parent.key, strict=True
                )
            ),
        )
        frame = frame.join(lookup, join_condition, "left")
        parent_present = reduce(
            lambda left, right: left & right,
            (functions.col(key).isNotNull() for key in parent.child_key),
        )
        checks.append(
            (
                parent_present & functions.col(marker).isNull(),
                functions.lit(missing_parent_reason(parent.entity, parent.attribute)),
            )
        )
        frame = frame.drop(*aliases.values())
    return frame, rdl_checked


def _append_enrich_check(
    spark: Any,
    frame: Any,
    checks: list[tuple[Any, Any]],
    target_table: str,
    metadata: EntityMetadata,
    config: SourceConfig,
    functions: Any,
) -> Any:
    if config.mode != "enrich":
        return frame
    target = spark.table(target_table)
    aliases = {key: f"_cfihos_enrich_key_{key}" for key in config.key}
    marker = "_cfihos_enrich_match"
    lookup = (
        target.select(*(target[key].alias(alias) for key, alias in aliases.items()))
        .distinct()
        .withColumn(marker, functions.lit(True))
    )
    condition = reduce(
        lambda left, right: left & right,
        (frame[key] == lookup[alias] for key, alias in aliases.items()),
    )
    frame = frame.join(lookup, condition, "left")
    checks.append(
        (
            functions.col(marker).isNull(),
            functions.lit(enrich_missing_reason(metadata.name)),
        )
    )
    return frame.drop(*aliases.values())


def _checked_frame(
    spark: Any,
    source_frame: Any,
    catalog: str,
    model: Mapping[str, Any],
    metadata: EntityMetadata,
    config: SourceConfig,
) -> Any:
    from pyspark.sql import Window
    from pyspark.sql import functions as F

    missing_source_columns = sorted(set(config.fields.values()) - set(source_frame.columns))
    if missing_source_columns:
        raise ValueError(
            f"source table is missing mapped columns: {', '.join(missing_source_columns)}"
        )

    raw_source_json = F.to_json(
        F.struct(*(source_frame[column].alias(column) for column in source_frame.columns)),
        {"ignoreNullFields": "false"},
    ).alias("_cfihos_source_row_json")
    selected = [raw_source_json]
    raw_names: dict[str, str] = {}
    prepared_names: dict[str, str] = {}
    for item in metadata.attributes:
        raw_name = f"_cfihos_raw_{item.name}"
        prepared_name = _prepared_column_name(item.name)
        raw_names[item.name] = raw_name
        prepared_names[item.name] = prepared_name
        if item.name in config.fields:
            raw = _normalized_column(source_frame[config.fields[item.name]], F)
        else:
            raw = F.lit(None).cast("string")
        selected.append(raw.alias(raw_name))
    frame = source_frame.select(*selected)

    checks: list[tuple[Any, Any]] = []
    required = set(config.key)
    if config.mode == "upsert":
        required.update(item.name for item in metadata.attributes if item.required)
    else:
        required.update(
            item.name
            for item in metadata.attributes
            if item.required and item.name in config.fields
        )

    for item in metadata.attributes:
        raw = F.col(raw_names[item.name])
        if item.name in required:
            checks.append((raw.isNull(), F.lit(missing_reason(item.name))))
        mapping = config.value_maps.get(item.name)
        if mapping:
            entries: list[Any] = []
            for source_value, standard_value in mapping.items():
                entries.extend((F.lit(source_value), F.lit(standard_value)))
            prepared = F.create_map(*entries).getItem(raw)
            checks.append(
                (
                    raw.isNotNull() & prepared.isNull(),
                    F.concat(
                        raw,
                        F.lit(
                            f" is not a valid {(item.reference or item.name).replace('_', ' ')}"
                        ),
                    ),
                )
            )
        else:
            prepared = raw
        frame = frame.withColumn(prepared_names[item.name], prepared)
        casted = _spark_cast(prepared_names[item.name], item.datatype, F)
        frame = frame.withColumn(item.name, casted)
        checks.append(
            (
                F.col(prepared_names[item.name]).isNotNull() & F.col(item.name).isNull(),
                F.concat(
                    F.col(prepared_names[item.name]),
                    F.lit(f" is not a valid {item.datatype.lower()} for {item.name}"),
                ),
            )
        )

    source_key = F.to_json(
        F.struct(*(F.col(key).alias(key) for key in config.key)),
        {"ignoreNullFields": "false"},
    )
    frame = frame.withColumn("_cfihos_source_key", source_key)
    target_table = _target_table(catalog, metadata)
    frame, _ = _append_lookup_checks(
        spark, frame, checks, catalog, model, metadata, config, F
    )
    frame = _append_enrich_check(
        spark, frame, checks, target_table, metadata, config, F
    )

    key_window = Window.partitionBy(*(F.col(key) for key in config.key))
    frame = frame.withColumn("_cfihos_key_count", F.count(F.lit(1)).over(key_window))
    occurrence_window = key_window.orderBy(F.col("_cfihos_source_row_json"))
    frame = frame.withColumn(
        "_cfihos_source_occurrence", F.row_number().over(occurrence_window)
    )
    checks.append(
        (
            F.col("_cfihos_key_count") > 1,
            F.lit("source key is duplicated"),
        )
    )
    reason_array = F.array(*(F.when(condition, reason) for condition, reason in checks))
    return frame.withColumn(
        "_cfihos_reasons",
        F.array_distinct(F.filter(reason_array, lambda reason: reason.isNotNull())),
    )


def _quarantine_rows(
    spark: Any,
    invalid: Any,
    catalog: str,
    config: SourceConfig,
    run_id: str,
) -> None:
    from pyspark.sql import functions as F

    incoming = invalid.select(
        F.lit(config.source).alias("source"),
        F.lit(config.into).alias("entity"),
        F.lit(run_id).alias("run_id"),
        F.col("_cfihos_source_key").alias("source_key"),
        F.col("_cfihos_source_occurrence").alias("source_occurrence"),
        F.col("_cfihos_source_row_json").alias("source_row_json"),
        F.col("_cfihos_reasons").alias("reasons"),
        F.current_timestamp().alias("quarantined_at"),
    )
    view = validate_identifier(f"cfihos_quarantine_{uuid.uuid4().hex}")
    incoming.createOrReplaceTempView(view)
    try:
        spark.sql(
            f"""MERGE INTO {catalog}.cfihos_quarantine.rows AS target
            USING {view} AS incoming
            ON target.source = incoming.source
              AND target.entity = incoming.entity
              AND target.source_key <=> incoming.source_key
              AND target.source_occurrence = incoming.source_occurrence
              AND target.source_row_json = incoming.source_row_json
              AND target.reasons = incoming.reasons
            WHEN NOT MATCHED THEN INSERT *"""
        )
    finally:
        spark.catalog.dropTempView(view)


def _merge_valid(
    spark: Any,
    valid: Any,
    target_table: str,
    metadata: EntityMetadata,
    config: SourceConfig,
) -> None:
    from pyspark.sql import functions as F

    target_columns = set(spark.table(target_table).columns)
    missing_target_columns = sorted(set(config.fields) - target_columns)
    if missing_target_columns:
        raise ValueError(
            "generated target table is missing model columns: "
            f"{', '.join(missing_target_columns)}"
        )
    mapped_columns = [name for name in config.fields if name in target_columns]
    selected = [F.col(name) for name in mapped_columns]
    technical_insert: list[str] = []
    for column in metadata.technical_columns:
        if column.name in target_columns:
            selected.append(_technical_expression(column, F).alias(column.name))
            technical_insert.append(column.name)
    incoming = valid.select(*selected)
    view = validate_identifier(f"cfihos_conform_{uuid.uuid4().hex}")
    incoming.createOrReplaceTempView(view)
    match = " AND ".join(
        f"target.`{key}` <=> incoming.`{key}`" for key in config.key
    )
    update_columns = [name for name in mapped_columns if name not in config.key]
    clauses: list[str] = []
    if update_columns:
        changed = " OR ".join(
            f"NOT (target.`{name}` <=> incoming.`{name}`)" for name in update_columns
        )
        assignments = ", ".join(
            f"target.`{name}` = incoming.`{name}`" for name in update_columns
        )
        clauses.append(f"WHEN MATCHED AND ({changed}) THEN UPDATE SET {assignments}")
    if config.mode == "upsert":
        insert_columns = [*mapped_columns, *technical_insert]
        columns_sql = ", ".join(f"`{name}`" for name in insert_columns)
        values_sql = ", ".join(f"incoming.`{name}`" for name in insert_columns)
        clauses.append(
            f"WHEN NOT MATCHED THEN INSERT ({columns_sql}) VALUES ({values_sql})"
        )
    if not clauses:
        spark.catalog.dropTempView(view)
        return
    try:
        spark.sql(
            f"MERGE INTO {target_table} AS target USING {view} AS incoming "
            f"ON {match} {' '.join(clauses)}"
        )
    finally:
        spark.catalog.dropTempView(view)


def conform(
    spark: Any,
    catalog: str,
    yaml_file: str | Path,
    model_file: str | Path = _DEFAULT_MODEL_FILE,
) -> dict[str, Any]:
    """Validate, conform, merge, quarantine, print, and return one run summary."""
    validate_identifier(catalog)
    model = load_model(model_file)
    config = validate_config(_load_yaml(_repository_path(yaml_file)), model)
    metadata = entity_metadata(model, config.into)
    source_table = _resolve_table(config.from_table, catalog)
    target_table = _target_table(catalog, metadata)
    if not spark.catalog.tableExists(source_table):
        raise ValueError(f"source table does not exist: {source_table}")
    if not spark.catalog.tableExists(target_table):
        raise ValueError(f"generated target table does not exist: {target_table}")
    _ensure_quarantine(spark, catalog)

    from pyspark.sql import functions as F

    run_id = str(uuid.uuid4())
    checked = _checked_frame(spark, spark.table(source_table), catalog, model, metadata, config)
    invalid = checked.where(F.size("_cfihos_reasons") > 0)
    valid = checked.where(F.size("_cfihos_reasons") == 0)
    landed = valid.count()
    quarantined = invalid.count()
    reasons_top = [
        {"reason": row.reason, "count": row["count"]}
        for row in (
            invalid.select(F.explode("_cfihos_reasons").alias("reason"))
            .groupBy("reason")
            .count()
            .orderBy(F.desc("count"), F.asc("reason"))
            .collect()
        )
    ]
    if quarantined:
        _quarantine_rows(spark, invalid, catalog, config, run_id)
    if landed:
        _merge_valid(spark, valid, target_table, metadata, config)

    summary = {
        "landed": landed,
        "quarantined": quarantined,
        "reasons_top": reasons_top,
    }
    print(json.dumps(summary, sort_keys=True))
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--yaml-file", type=Path, required=True)
    parser.add_argument("--model-file", type=Path, default=_DEFAULT_MODEL_FILE)
    args = parser.parse_args(argv)
    from pyspark.sql import SparkSession

    conform(
        SparkSession.builder.getOrCreate(),
        args.catalog,
        args.yaml_file,
        args.model_file,
    )
    return 0


if __name__ == "__main__":
    main()
