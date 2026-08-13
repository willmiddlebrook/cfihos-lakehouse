"""Validate an agent-authored mapping proposal against its pinned inputs."""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

_SCRIPT_PATH = Path(__file__).resolve()
try:
    from src.onramp.config_contract import validate_value_map_targets
except ModuleNotFoundError:
    sys.path.insert(0, str(_SCRIPT_PATH.parents[1]))
    from onramp.config_contract import validate_value_map_targets

TIERS = {"certain", "probable"}
EVIDENCE_KINDS = {
    "name_similarity",
    "definition_match",
    "sample_fit",
    "picklist_coverage",
}


def _load_mapping(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return value


def _is_non_empty_sentence(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_utc_timestamp(value: Any) -> bool:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return False
    else:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() == timezone.utc.utcoffset(parsed)


def _candidate_mappings(candidate: dict[str, Any]) -> Counter[tuple[str, str, str]]:
    mappings: Counter[tuple[str, str, str]] = Counter()
    feeds = candidate.get("feeds", {})
    if not isinstance(feeds, dict):
        return mappings
    for entity, feed in feeds.items():
        if not isinstance(entity, str) or not isinstance(feed, dict):
            continue
        fields = feed.get("fields", {})
        if not isinstance(fields, dict):
            continue
        for attribute, source_column in fields.items():
            if isinstance(attribute, str) and isinstance(source_column, str):
                mappings[(entity, attribute, source_column)] += 1
    return mappings


def _source_id_columns(candidate: dict[str, Any]) -> Counter[str]:
    columns: Counter[str] = Counter()
    feeds = candidate.get("feeds", {})
    if not isinstance(feeds, dict):
        return columns
    for feed in feeds.values():
        if isinstance(feed, dict) and isinstance(feed.get("source_id"), str):
            columns[feed["source_id"]] += 1
    return columns


def _profile_columns(profile: dict[str, Any], errors: list[str]) -> Counter[str]:
    tables = profile.get("tables")
    if tables is None and isinstance(profile.get("columns"), list):
        tables = [profile]
    if not isinstance(tables, list) or not tables:
        errors.append("profile must contain columns or a non-empty tables list")
        return Counter()
    columns: Counter[str] = Counter()
    for table_index, table in enumerate(tables):
        if not isinstance(table, dict) or not isinstance(table.get("columns"), list):
            errors.append(f"profile tables[{table_index}].columns must be a list")
            continue
        for column_index, column in enumerate(table["columns"]):
            if not isinstance(column, dict) or not _is_non_empty_sentence(column.get("name")):
                errors.append(
                    f"profile tables[{table_index}].columns[{column_index}] needs a name"
                )
                continue
            columns[column["name"]] += 1
    return columns


def _format_mapping(mapping: tuple[str, str, str]) -> str:
    return f"{mapping[0]}.{mapping[1]} <- {mapping[2]}"


def _validate_mappings(
    proposal: dict[str, Any], candidate: dict[str, Any], errors: list[str]
) -> Counter[str]:
    expected = _candidate_mappings(candidate)
    actual: Counter[tuple[str, str, str]] = Counter()
    mapped_columns: Counter[str] = Counter()
    mappings = proposal.get("mappings")
    if not isinstance(mappings, list) or not mappings:
        errors.append("mappings must be a non-empty list")
        return mapped_columns
    for index, mapping in enumerate(mappings):
        if not isinstance(mapping, dict):
            errors.append(f"mappings[{index}] must be a mapping")
            continue
        values = tuple(mapping.get(key) for key in ("entity", "attribute", "source_column"))
        if not all(_is_non_empty_sentence(value) for value in values):
            errors.append(f"mappings[{index}] needs entity, attribute, and source_column")
        else:
            typed_values = (str(values[0]), str(values[1]), str(values[2]))
            actual[typed_values] += 1
            mapped_columns[typed_values[2]] += 1
        tier = mapping.get("tier")
        if tier not in TIERS:
            errors.append(f"mappings[{index}].tier must be certain or probable")
        evidence = mapping.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"mappings[{index}].evidence must be non-empty")
            continue
        kinds: set[str] = set()
        for evidence_index, item in enumerate(evidence):
            if not isinstance(item, dict) or item.get("kind") not in EVIDENCE_KINDS:
                errors.append(
                    f"mappings[{index}].evidence[{evidence_index}].kind is not allowed"
                )
                continue
            kinds.add(item["kind"])
            if not _is_non_empty_sentence(item.get("note")):
                errors.append(
                    f"mappings[{index}].evidence[{evidence_index}].note must be non-empty"
                )
        if tier == "certain" and len(kinds) < 2:
            errors.append(f"mappings[{index}] certain tier requires at least 2 evidence kinds")

    for mapping, count in (expected - actual).items():
        errors.append(f"proposal is missing candidate mapping {_format_mapping(mapping)} x{count}")
    for mapping, count in (actual - expected).items():
        errors.append(f"proposal has non-candidate mapping {_format_mapping(mapping)} x{count}")
    return mapped_columns


def _validate_abstentions(
    proposal: dict[str, Any], candidate: dict[str, Any], errors: list[str]
) -> tuple[Counter[str], Counter[str]]:
    abstained = proposal.get("abstained")
    if not isinstance(abstained, dict):
        errors.append("abstained must be a mapping with columns and codes lists")
        return Counter(), Counter()
    columns: Counter[str] = Counter()
    for index, item in enumerate(abstained.get("columns", [])):
        if not isinstance(item, dict) or not _is_non_empty_sentence(item.get("source_column")):
            errors.append(f"abstained.columns[{index}] needs source_column")
            continue
        if not _is_non_empty_sentence(item.get("reason")):
            errors.append(f"abstained.columns[{index}].reason must be non-empty")
        columns[item["source_column"]] += 1

    codes: Counter[str] = Counter()
    value_maps = candidate.get("value_maps", {})
    value_maps = value_maps if isinstance(value_maps, dict) else {}
    code_items = abstained.get("codes", [])
    if not isinstance(code_items, list):
        errors.append("abstained.codes must be a list")
        return columns, codes
    for index, item in enumerate(code_items):
        if not isinstance(item, dict) or not _is_non_empty_sentence(item.get("key")):
            errors.append(f"abstained.codes[{index}] needs key")
            continue
        key = item["key"]
        if key not in value_maps:
            errors.append(f"abstained.codes[{index}].key {key} has no candidate value_map")
        if "source_value" not in item:
            errors.append(f"abstained.codes[{index}] needs source_value")
        elif isinstance(value_maps.get(key), dict) and item["source_value"] in value_maps[key]:
            errors.append(f"abstained code {key}={item['source_value']!r} is already mapped")
        if not _is_non_empty_sentence(item.get("reason")):
            errors.append(f"abstained.codes[{index}].reason must be non-empty")
        codes[key] += 1
    return columns, codes


def _validate_value_map_summaries(
    proposal: dict[str, Any],
    candidate: dict[str, Any],
    abstained_codes: Counter[str],
    errors: list[str],
) -> None:
    candidate_maps = candidate.get("value_maps", {})
    candidate_maps = candidate_maps if isinstance(candidate_maps, dict) else {}
    summaries = proposal.get("value_map_summaries")
    if not isinstance(summaries, list):
        errors.append("value_map_summaries must be a list")
        return
    actual_keys: Counter[str] = Counter()
    for index, summary in enumerate(summaries):
        if not isinstance(summary, dict) or not _is_non_empty_sentence(summary.get("key")):
            errors.append(f"value_map_summaries[{index}] needs key")
            continue
        key = summary["key"]
        actual_keys[key] += 1
        counts = {name: summary.get(name) for name in ("distinct_seen", "mapped", "abstained")}
        if any(not isinstance(value, int) or value < 0 for value in counts.values()):
            errors.append(f"value_map_summaries[{index}] counts must be non-negative integers")
            continue
        if counts["mapped"] + counts["abstained"] != counts["distinct_seen"]:
            errors.append(
                f"value_map_summaries[{index}] mapped + abstained must equal distinct_seen"
            )
        mapping = candidate_maps.get(key)
        if isinstance(mapping, dict) and counts["mapped"] != len(mapping):
            errors.append(
                f"value_map_summaries[{index}].mapped must equal the candidate value_map size"
            )
        if counts["abstained"] != abstained_codes[key]:
            errors.append(
                f"value_map_summaries[{index}].abstained must equal abstained.codes entries"
            )
    expected_keys = Counter({key: 1 for key in candidate_maps})
    for key, count in (expected_keys - actual_keys).items():
        errors.append(f"value_map_summaries is missing candidate value_map {key} x{count}")
    for key, count in (actual_keys - expected_keys).items():
        errors.append(f"value_map_summaries has non-candidate key {key} x{count}")


def _validate_unverifiable_acknowledgements(
    proposal: dict[str, Any], required_keys: set[str], errors: list[str]
) -> None:
    acknowledgements = proposal.get("unverifiable_targets", [])
    if not isinstance(acknowledgements, list):
        errors.append("unverifiable_targets must be a list")
        return
    actual: Counter[str] = Counter()
    for index, acknowledgement in enumerate(acknowledgements):
        if not isinstance(acknowledgement, dict) or not _is_non_empty_sentence(
            acknowledgement.get("key")
        ):
            errors.append(f"unverifiable_targets[{index}] needs key")
            continue
        key = acknowledgement["key"]
        actual[key] += 1
        if not _is_non_empty_sentence(acknowledgement.get("basis")):
            errors.append(f"unverifiable_targets[{index}].basis must be non-empty")
    expected = Counter({key: 1 for key in required_keys})
    for key, count in (expected - actual).items():
        errors.append(
            f"unverifiable value_map {key} needs an acknowledgement with a basis x{count}"
        )
    for key, count in (actual - expected).items():
        errors.append(f"unverifiable_targets acknowledges a verified or unknown key {key} x{count}")


def validate_proposal(
    proposal_path: Path, candidate_path: Path, repo_root: Path | None = None
) -> list[str]:
    """Return every proposal-contract error; an empty list means approval-ready."""

    root = (repo_root or _SCRIPT_PATH.parents[2]).resolve()
    proposal_path = proposal_path if proposal_path.is_absolute() else root / proposal_path
    candidate_path = candidate_path if candidate_path.is_absolute() else root / candidate_path
    try:
        proposal = _load_mapping(proposal_path)
        candidate = _load_mapping(candidate_path)
        model = _load_mapping(root / "model" / "model.yml")
    except (OSError, ValueError, yaml.YAMLError) as error:
        return [str(error)]

    errors: list[str] = []
    if proposal.get("proposal_version") != 1:
        errors.append("proposal_version must be 1")
    source = proposal.get("source")
    if not _is_non_empty_sentence(source):
        errors.append("proposal source must be non-empty")
        source = ""
    if candidate.get("source") != source:
        errors.append("proposal source must equal candidate source")
    if source and proposal_path.name != f"{source}.proposal.yml":
        errors.append("proposal filename must be <source>.proposal.yml")
    if source and candidate_path.name != f"{source}.yml":
        errors.append("candidate filename must be <source>.yml")
    if not _is_non_empty_sentence(proposal.get("generated_by")):
        errors.append("generated_by must be non-empty")
    if not _is_utc_timestamp(proposal.get("generated_at")):
        errors.append("generated_at must be an ISO-8601 UTC timestamp")

    pins = proposal.get("pins")
    if not isinstance(pins, dict):
        errors.append("pins must be a mapping")
        pins = {}
    expected_model_hash = model.get("metadata", {}).get("source_sha256")
    if pins.get("model_sha256") != expected_model_hash:
        errors.append("stale model_sha256 pin")
    expected_rdl_version = str(model.get("metadata", {}).get("cfihos_version", ""))
    if str(pins.get("rdl_version", "")) != expected_rdl_version:
        errors.append("rdl_version pin must equal model metadata.cfihos_version")

    expected_profile_file = Path("src/onramp/profiles") / f"{source}.yml"
    profile_file_value = pins.get("profile_file")
    profile: dict[str, Any] = {}
    if not isinstance(profile_file_value, str) or Path(profile_file_value) != expected_profile_file:
        errors.append(f"profile_file must be {expected_profile_file.as_posix()}")
    else:
        profile_path = (root / profile_file_value).resolve()
        try:
            profile_path.relative_to(root)
            profile = _load_mapping(profile_path)
            actual_hash = hashlib.sha256(profile_path.read_bytes()).hexdigest()
            if pins.get("profile_sha256") != actual_hash:
                errors.append("stale profile_sha256 pin")
        except (OSError, ValueError, yaml.YAMLError) as error:
            errors.append(str(error))
    if profile and profile.get("source") != source:
        errors.append("profile source must equal proposal and candidate source")

    mapped_columns = _validate_mappings(proposal, candidate, errors)
    abstained_columns, abstained_codes = _validate_abstentions(proposal, candidate, errors)
    profile_columns = _profile_columns(profile, errors) if profile else Counter()
    accounted_columns = mapped_columns + _source_id_columns(candidate) + abstained_columns
    for column, count in (profile_columns - accounted_columns).items():
        errors.append(
            f"profile column {column} is missing from "
            f"mappings/source_ids/abstentions x{count}"
        )
    for column, count in (accounted_columns - profile_columns).items():
        errors.append(
            f"column {column} is accounted for more often than it appears in profile x{count}"
        )

    _validate_value_map_summaries(proposal, candidate, abstained_codes, errors)
    for rationale in ("match_on_rationale", "wins_rank_rationale"):
        if not _is_non_empty_sentence(proposal.get(rationale)):
            errors.append(f"{rationale} must be non-empty")

    target_result = validate_value_map_targets(candidate, model, root / "spec" / "rdl")
    errors.extend(target_result.errors)
    _validate_unverifiable_acknowledgements(
        proposal, {warning.key for warning in target_result.warnings}, errors
    )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("proposal", type=Path)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=_SCRIPT_PATH.parents[2])
    args = parser.parse_args(argv)
    errors = validate_proposal(args.proposal, args.candidate, args.repo_root)
    if errors:
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print(f"proposal contract valid: {args.proposal}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
