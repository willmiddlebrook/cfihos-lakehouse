"""Generic stage → translate → match → publish → report engine."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from functools import reduce
from pathlib import Path
from typing import Any

import yaml

try:
    from src.identifiers import validate_identifier
except ModuleNotFoundError:  # Serverless Python-file tasks put src/ on sys.path.
    sys.path.insert(0, str(Path(globals().get("__file__", sys.argv[0])).resolve().parents[1]))
    from identifiers import validate_identifier

_SCRIPT_PATH = Path(globals().get("__file__", sys.argv[0])).resolve()


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return value


def validate_config(config: dict[str, Any], model: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    generated_entities = set(
        model.get("generation", {}).get("spine_entities", [])
        if isinstance(model.get("generation"), dict)
        else []
    )
    source = config.get("source")
    try:
        validate_identifier(source)
    except ValueError:
        errors.append("source must be a lowercase SQL identifier")
    if config.get("arrives_as") != "table":
        errors.append("arrives_as must be table")
    if config.get("origination", "steward_only") not in {"founding", "steward_only"}:
        errors.append("origination must be founding or steward_only")
    if config.get("unmatched") != "review_queue":
        errors.append("unmatched must be review_queue")
    feeds = config.get("feeds")
    if not isinstance(feeds, dict) or not feeds:
        errors.append("feeds must be a non-empty mapping")
        feeds = {}
    for entity_name, feed in feeds.items():
        if entity_name not in model["entities"]:
            errors.append(f"feed {entity_name}: not present in model.yml")
            continue
        if entity_name not in generated_entities:
            errors.append(
                f"feed {entity_name}: entity is not selected in "
                "model.generation.spine_entities and has no deployed registry table"
            )
        if not isinstance(feed, dict):
            errors.append(f"feed {entity_name}: must be a mapping")
            continue
        for key in ("from", "source_id", "match_on", "fields"):
            if not feed.get(key):
                errors.append(f"feed {entity_name}: missing {key}")
        fields = feed.get("fields", {})
        if not isinstance(fields, dict):
            errors.append(f"feed {entity_name}: fields must be a mapping")
            fields = {}
        attributes = {item["name"] for item in model["entities"][entity_name]["attributes"]}
        for attribute in fields:
            if attribute not in attributes:
                errors.append(f"feed {entity_name}: unknown canonical attribute {attribute}")
        for attribute in feed.get("match_on", []):
            if attribute not in fields:
                errors.append(f"feed {entity_name}: match key {attribute} has no field mapping")
    claims = config.get("claims")
    if not isinstance(claims, dict):
        errors.append("claims must be a mapping")
        claims = {}
    for key, claim in claims.items():
        if "." not in key:
            errors.append(f"claim {key}: key must be entity.attribute")
            continue
        entity_name, attribute = key.split(".", 1)
        if entity_name not in feeds:
            errors.append(f"claim {key}: entity has no feed")
            continue
        feed = feeds[entity_name]
        if not isinstance(feed, dict):
            errors.append(f"claim {key}: entity feed is not a mapping")
            continue
        fields = feed.get("fields", {})
        fields = fields if isinstance(fields, dict) else {}
        if attribute not in fields:
            errors.append(f"claim {key}: attribute has no feed field mapping")
        if not isinstance(claim, dict):
            errors.append(f"claim {key}: wins_rank must be an integer")
            errors.append(f"claim {key}: field must equal its feed field mapping")
            continue
        if not isinstance(claim.get("wins_rank"), int):
            errors.append(f"claim {key}: wins_rank must be an integer")
        elif claim["wins_rank"] < 1:
            errors.append(f"claim {key}: wins_rank must be positive")
        expected_field = fields.get(attribute)
        if claim.get("field") != expected_field:
            errors.append(
                f"claim {key}: field must equal feed mapping {expected_field!r}, "
                f"found {claim.get('field')!r}"
            )
    value_maps = config.get("value_maps")
    if not isinstance(value_maps, dict):
        errors.append("value_maps must be a mapping")
    else:
        for key, mapping in value_maps.items():
            if key not in claims:
                errors.append(f"value map {key}: no corresponding claim")
            if not isinstance(mapping, dict) or not mapping:
                errors.append(f"value map {key}: must be a non-empty mapping")
    if config.get("origination", "steward_only") == "founding":
        claimed = {
            key
            for key in claims
            if isinstance(key, str) and "." in key
        }
        for entity_name in feeds:
            if entity_name not in model["entities"]:
                continue
            required_claims = {
                f"{entity_name}.{item['name']}"
                for item in model["entities"][entity_name]["attributes"]
                if item["requirement"] in {"identifier", "mandatory"}
            }
            missing_claims = sorted(required_claims - claimed)
            if missing_claims:
                errors.append(
                    f"founding feed {entity_name}: missing required claims "
                    + ", ".join(missing_claims)
                )
    try:
        from src.onramp.config_contract import validate_value_map_targets
    except ModuleNotFoundError:  # Serverless Python-file tasks put src/ on sys.path.
        from onramp.config_contract import validate_value_map_targets

    target_result = validate_value_map_targets(
        config, model, _SCRIPT_PATH.parents[2] / "spec" / "rdl"
    )
    errors.extend(target_result.errors)
    return errors


def validate_config_warnings(
    config: dict[str, Any], model: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return structured warnings for targets that Core RDL cannot verify."""
    try:
        from src.onramp.config_contract import validate_value_map_targets
    except ModuleNotFoundError:  # Serverless Python-file tasks put src/ on sys.path.
        from onramp.config_contract import validate_value_map_targets

    return [
        warning.as_dict()
        for warning in validate_value_map_targets(
            config, model, _SCRIPT_PATH.parents[2] / "spec" / "rdl"
        ).warnings
    ]


def normalize_value(value: Any, strip_prefixes: Iterable[str] = ()) -> str:
    normalized = " ".join(str(value or "").strip().casefold().split())
    for prefix in strip_prefixes:
        normalized_prefix = " ".join(str(prefix).strip().casefold().split())
        if normalized.startswith(normalized_prefix):
            return normalized[len(normalized_prefix) :].strip()
    return normalized


def unmapped_exception_id(
    source: str, source_id: Any, key: str, source_value: Any
) -> str:
    """Return the stable identity of one specific untranslated source value."""
    payload = "|".join(str(value) for value in (source, source_id, key, source_value))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MatchResult:
    tier: str | None
    spine_id: str | None
    reason: str | None


def match_record(
    staged: dict[str, Any],
    candidates: Iterable[dict[str, Any]],
    match_on: list[str],
    strip_prefixes: Iterable[str] = (),
) -> MatchResult:
    exact = [
        candidate
        for candidate in candidates
        if all(staged.get(key) == candidate.get(key) for key in match_on)
    ]
    if len(exact) == 1:
        return MatchResult("exact", exact[0]["spine_id"], None)
    if len(exact) > 1:
        return MatchResult(None, None, "multiple exact candidates")
    normalized = [
        candidate
        for candidate in candidates
        if all(
            normalize_value(staged.get(key), strip_prefixes)
            == normalize_value(candidate.get(key), strip_prefixes)
            for key in match_on
        )
    ]
    if len(normalized) == 1:
        return MatchResult("normalized", normalized[0]["spine_id"], None)
    if len(normalized) > 1:
        return MatchResult(None, None, "multiple normalized candidates")
    return MatchResult(None, None, "no exact or normalized candidate")


def process_rows(
    config: dict[str, Any],
    entity_name: str,
    rows: Iterable[dict[str, Any]],
    candidates: Iterable[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Pure fixture engine used by defect and contract tests."""
    feed = config["feeds"][entity_name]
    prefixes = config.get("normalization", {}).get("strip_prefixes", [])
    claims = {
        key.split(".", 1)[1]: value
        for key, value in config["claims"].items()
        if key.startswith(f"{entity_name}.")
    }
    translated: list[dict[str, Any]] = []
    unmapped: list[dict[str, Any]] = []
    matched: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    for source_row in rows:
        staged = {
            canonical: source_row.get(source_column)
            for canonical, source_column in feed["fields"].items()
        }
        staged["_source_id"] = source_row.get(feed["source_id"])
        blocked = False
        for attribute in claims:
            key = f"{entity_name}.{attribute}"
            mapping = config.get("value_maps", {}).get(key)
            if mapping is None:
                continue
            source_value = staged.get(attribute)
            if source_value not in mapping:
                unmapped.append(
                    {
                        "exception_id": unmapped_exception_id(
                            config["source"], staged["_source_id"], key, source_value
                        ),
                        "source_id": staged["_source_id"],
                        "attribute": attribute,
                        "source_value": source_value,
                    }
                )
                blocked = True
            else:
                staged[attribute] = mapping[source_value]
        translated.append(staged)
        if blocked:
            continue
        result = match_record(staged, candidates, feed["match_on"], prefixes)
        output = {**staged, "spine_id": result.spine_id, "match_tier": result.tier}
        if result.spine_id:
            matched.append(output)
        else:
            review.append({**output, "reason": result.reason})
    return {"translated": translated, "unmapped": unmapped, "matched": matched, "review": review}


def _normalized_column(column: Any, prefixes: list[str], functions: Any) -> Any:
    value = functions.lower(functions.trim(functions.regexp_replace(column, r"\s+", " ")))
    for prefix in prefixes:
        value = functions.regexp_replace(value, f"^{re.escape(prefix.casefold())}", "")
    return functions.trim(value)


def _target_table(catalog: str, entity: dict[str, Any]) -> str:
    return f"{catalog}.cfihos_{entity['subject_area']}.{entity['name']}"


def _sync_config(spark: Any, catalog: str, config: dict[str, Any], raw_yaml: str) -> None:
    from pyspark.sql import functions as F

    validate_identifier(catalog)
    table = f"{catalog}.cfihos_onramp.source_config"
    source = validate_identifier(config["source"])
    spark.sql(f"DELETE FROM {table} WHERE source = '{source}'")
    frame = spark.createDataFrame(
        [(source, raw_yaml, hashlib.sha256(raw_yaml.encode()).hexdigest())],
        "source string, config_yaml string, config_hash string",
    ).withColumn("deployed_at", F.current_timestamp())
    frame.write.mode("append").saveAsTable(table)


def run_spark(
    spark: Any,
    catalog: str,
    config: dict[str, Any],
    model: dict[str, Any],
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run one transformation path, guarding only its state-changing sinks."""
    validate_identifier(catalog)
    from pyspark.sql import functions as F

    try:
        from src.trust.materialize import materialize_entities
        from src.trust.who_wins import publish_claims
    except ModuleNotFoundError:  # Serverless Python-file tasks put src/ on sys.path.
        sys.path.insert(0, str(_SCRIPT_PATH.parents[1]))
        from trust.materialize import materialize_entities
        from trust.who_wins import publish_claims

    run_id = str(uuid.uuid4())
    source = validate_identifier(config["source"])
    prefixes = config.get("normalization", {}).get("strip_prefixes", [])
    founding = config.get("origination", "steward_only") == "founding"
    entity_reports: dict[str, dict[str, Any]] = {}
    for entity_name, feed in config["feeds"].items():
        entity = model["entities"][entity_name]
        source_frame = spark.table(feed["from"])
        projections = [F.col(feed["source_id"]).cast("string").alias("_source_id")]
        projections.extend(
            F.col(source_column).alias(canonical)
            for canonical, source_column in feed["fields"].items()
        )
        staged = source_frame.select(*projections)
        input_rows = staged.count()
        blocked = None
        unknown_frames = []
        for key, mapping in config.get("value_maps", {}).items():
            mapped_entity, attribute = key.split(".", 1)
            if mapped_entity != entity_name:
                continue
            source_value = F.col(attribute).cast("string")
            allowed = [str(value) for value in mapping]
            unknown = staged.filter(source_value.isNotNull() & ~source_value.isin(allowed)).select(
                F.sha2(
                    F.concat_ws(
                        "|",
                        F.lit(source),
                        F.col("_source_id"),
                        F.lit(key),
                        source_value,
                    ),
                    256,
                ).alias("exception_id"),
                F.lit(run_id).alias("run_id"),
                F.lit(source).alias("source"),
                F.col("_source_id").alias("source_id"),
                F.lit(entity_name).alias("entity"),
                F.lit(attribute).alias("attribute"),
                source_value.alias("source_value"),
                F.current_timestamp().alias("recorded_at"),
            )
            unknown_frames.append(unknown)
            ids = unknown.select("source_id").distinct()
            blocked = ids if blocked is None else blocked.unionByName(ids).distinct()
            entries = []
            for old, new in mapping.items():
                entries.extend((F.lit(str(old)), F.lit(str(new))))
            staged = staged.withColumn(attribute, F.create_map(*entries)[source_value])
        unmapped_summary: list[dict[str, Any]] = []
        if unknown_frames:
            unknown_candidates = reduce(
                lambda left, right: left.unionByName(right), unknown_frames
            )
            existing_exceptions = spark.table(
                f"{catalog}.cfihos_onramp.unmapped_codes"
            ).select("exception_id")
            unknown_to_write = unknown_candidates.join(
                existing_exceptions, "exception_id", "left_anti"
            )
            if not dry_run:
                unknown_to_write.write.mode("append").saveAsTable(
                    f"{catalog}.cfihos_onramp.unmapped_codes"
                )
            summary_rows = (
                unknown_candidates.groupBy(
                    F.concat_ws(".", "entity", "attribute").alias("key"), "source_value"
                )
                .agg(F.count(F.lit(1)).alias("rows"))
                .orderBy(F.desc("rows"), "key", "source_value")
                .limit(50)
                .collect()
            )
            unmapped_summary = [row.asDict(recursive=True) for row in summary_rows]
        eligible = staged if blocked is None else staged.join(
            blocked, staged._source_id == blocked.source_id, "left_anti"
        )

        existing = spark.table(f"{catalog}.cfihos_trust.id_map").filter(
            (F.col("source_system") == source) & (F.col("entity") == entity_name)
        )
        direct = eligible.join(existing, eligible._source_id == existing.source_id, "inner").select(
            eligible["*"], existing.spine_id, existing.match_tier
        )
        remaining = eligible.join(existing, eligible._source_id == existing.source_id, "left_anti")
        target = spark.table(_target_table(catalog, entity)).filter(F.col("is_current"))

        exact_condition = reduce(
            lambda left, right: left & right,
            [remaining[key].eqNullSafe(target[key]) for key in feed["match_on"]],
        )
        exact_candidates = remaining.join(target, exact_condition, "inner").select(
            remaining["*"], target.spine_id
        )
        exact_counts = exact_candidates.groupBy("_source_id").agg(
            F.countDistinct("spine_id").alias("candidate_count"),
            F.first("spine_id").alias("spine_id"),
        )
        exact = remaining.join(
            exact_counts.filter(F.col("candidate_count") == 1), "_source_id", "inner"
        ).withColumn("match_tier", F.lit("exact"))
        no_exact = remaining.join(exact_counts, "_source_id", "left_anti")

        normalized_condition = reduce(
            lambda left, right: left & right,
            [
                _normalized_column(no_exact[key], prefixes, F).eqNullSafe(
                    _normalized_column(target[key], prefixes, F)
                )
                for key in feed["match_on"]
            ],
        )
        normalized_candidates = no_exact.join(target, normalized_condition, "inner").select(
            no_exact["*"], target.spine_id
        )
        normalized_counts = normalized_candidates.groupBy("_source_id").agg(
            F.countDistinct("spine_id").alias("candidate_count"),
            F.first("spine_id").alias("spine_id"),
        )
        normalized = no_exact.join(
            normalized_counts.filter(F.col("candidate_count") == 1), "_source_id", "inner"
        ).withColumn("match_tier", F.lit("normalized"))
        matched = direct.unionByName(exact, allowMissingColumns=True).unionByName(
            normalized, allowMissingColumns=True
        )
        unresolved = eligible.join(matched.select("_source_id"), "_source_id", "left_anti")
        if founding:
            founding_matches = unresolved.withColumn(
                "spine_id",
                F.concat(
                    F.lit("sp-"),
                    F.substring(
                        F.sha2(
                            F.concat(
                                F.lit(f"spine|{entity_name}|{source}|"), F.col("_source_id")
                            ),
                            256,
                        ),
                        1,
                        24,
                    ),
                ),
            ).withColumn("match_tier", F.lit("founding"))
            queue_input = unresolved.filter(F.lit(False))
        else:
            founding_matches = matched.filter(F.lit(False))
            queue_input = unresolved
        resolved = matched.unionByName(founding_matches, allowMissingColumns=True)
        queue_id = F.sha2(
            F.concat_ws("|", F.lit(source), F.lit(entity_name), F.col("_source_id")), 256
        )
        queue = queue_input.select(
            queue_id.alias("queue_id"),
            F.lit(run_id).alias("run_id"),
            F.lit(source).alias("source_system"),
            F.lit(entity_name).alias("entity"),
            F.col("_source_id").alias("source_id"),
            F.lit(None).cast("string").alias("candidate_spine_id"),
            F.to_json(F.struct(*[F.col(key) for key in feed["match_on"]])).alias("evidence"),
            F.lit("No unique exact or normalized match").alias("reason"),
            F.lit("open").alias("status"),
            F.lit(None).cast("string").alias("resolved_by"),
            F.lit(None).cast("timestamp").alias("resolved_at"),
            F.current_timestamp().alias("created_at"),
        )
        existing_queue = spark.table(f"{catalog}.cfihos_trust.review_queue").select("queue_id")
        queue_to_write = queue.join(existing_queue, "queue_id", "left_anti")
        blocked_rows = 0 if blocked is None else blocked.count()
        already_mapped = direct.count()
        exact_rows = exact.count()
        normalized_rows = normalized.count()
        founding_rows = founding_matches.count()
        queued_rows = queue_to_write.count()
        covered = already_mapped + exact_rows + normalized_rows + founding_rows
        entity_reports[entity_name] = {
            "input_rows": input_rows,
            "blocked_rows": blocked_rows,
            "unmapped_codes": unmapped_summary,
            "already_mapped": already_mapped,
            "exact": exact_rows,
            "normalized": normalized_rows,
            "would_found": founding_rows,
            "queued": queued_rows,
            "coverage": covered / input_rows if input_rows else 0.0,
        }
        if not dry_run:
            # Confirmed items become direct next run; rejection is a decision, not a snooze.
            queue_to_write.write.mode("append").saveAsTable(
                f"{catalog}.cfihos_trust.review_queue"
            )

        # Direct rows already exist in the crosswalk and must never flow back into new maps.
        new_matches = exact.unionByName(normalized, allowMissingColumns=True).unionByName(
            founding_matches, allowMissingColumns=True
        )
        new_maps = new_matches.select(
            F.lit(source).alias("source_system"),
            F.lit(entity_name).alias("entity"),
            F.col("_source_id").alias("source_id"),
            "spine_id",
            "match_tier",
            F.current_timestamp().alias("matched_at"),
            F.lit("onramp_engine").alias("matched_by"),
        )
        if not dry_run:
            new_maps.write.mode("append").saveAsTable(f"{catalog}.cfihos_trust.id_map")

        for key, claim in config["claims"].items():
            claim_entity, attribute = key.split(".", 1)
            if claim_entity != entity_name:
                continue
            values = resolved.filter(F.col(attribute).isNotNull()).select(
                F.lit(run_id).alias("run_id"),
                F.lit(source).alias("source_system"),
                F.lit(entity_name).alias("entity"),
                "spine_id",
                F.lit(attribute).alias("attribute"),
                F.col(attribute).cast("string").alias("value"),
                F.lit(claim["wins_rank"]).alias("wins_rank"),
                F.current_timestamp().alias("observed_at"),
            )
            if not dry_run:
                # Claims intentionally remain append-per-run; retention is a future concern.
                # Publication is scoped to run_id, so retained history does not republish itself.
                values.write.mode("append").saveAsTable(
                    f"{catalog}.cfihos_onramp.staged_claims"
                )

    if not dry_run:
        publish_claims(spark, catalog, run_id)
        materialize_entities(spark, catalog, model, config["feeds"])
    return {
        "mode": "dry_run" if dry_run else "live",
        "source": source,
        "run_id": run_id,
        "entities": entity_reports,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--model", type=Path, default=_SCRIPT_PATH.parents[2] / "model" / "model.yml"
    )
    parser.add_argument("--dry-run", action="store_true")
    raw_arguments = list(sys.argv[1:] if argv is None else argv)
    normalized_arguments: list[str] = []
    for argument in raw_arguments:
        if argument == "--dry-run=true":
            normalized_arguments.append("--dry-run")
        elif argument != "--dry-run=false":
            normalized_arguments.append(argument)
    args = parser.parse_args(normalized_arguments)
    validate_identifier(args.catalog)
    root = _SCRIPT_PATH.parents[2]
    config_path = args.config
    if not config_path.exists():
        config_path = root / "src" / "onramp" / "sources" / args.config.name
    model_path = args.model if args.model.exists() else root / "model" / "model.yml"
    raw_config = config_path.read_text(encoding="utf-8").replace("${catalog}", args.catalog)
    config = yaml.safe_load(raw_config)
    if not isinstance(config, dict):
        raise ValueError(f"{config_path} must contain a YAML mapping")
    model = load_yaml(model_path)
    errors = validate_config(config, model)
    if errors:
        raise ValueError("invalid source config:\n- " + "\n- ".join(errors))
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    if not args.dry_run:
        _sync_config(spark, args.catalog, config, raw_config)
    report = run_spark(spark, args.catalog, config, model, dry_run=args.dry_run)
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    main()
