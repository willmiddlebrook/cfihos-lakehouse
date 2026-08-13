"""Lint all source contracts together and print their safe run order."""

from __future__ import annotations

import argparse
import heapq
import itertools
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

import yaml

_SCRIPT_PATH = Path(globals().get("__file__", sys.argv[0])).resolve()
ROOT = _SCRIPT_PATH.parents[1]
DEFAULT_SOURCES = ROOT / "src" / "conform" / "sources"
DEFAULT_MODEL = ROOT / "model" / "model.yml"


class SourceContractError(ValueError):
    """One or more source contracts cannot safely run together."""


@dataclass(frozen=True)
class SourceContract:
    path: Path
    source: str
    entity: str
    key: tuple[str, ...]
    mode: str
    territory: str | None
    fields: dict[str, str]


@dataclass(frozen=True)
class TerritoryPair:
    entity: str
    attribute: str
    left_source: str
    left_territory: str
    right_source: str
    right_territory: str


@dataclass(frozen=True)
class SourceReport:
    run_order: tuple[str, ...]
    ownership: tuple[tuple[str, str, str], ...]
    territory_pairs: tuple[TerritoryPair, ...]

    def render(self) -> str:
        lines = [
            "Run order: " + " -> ".join(_pluralize(entity) for entity in self.run_order),
            "Ownership matrix:",
            "entity | attribute | source",
            "--- | --- | ---",
        ]
        lines.extend(" | ".join(row) for row in self.ownership)
        if self.territory_pairs:
            lines.append("Territory pairings for human review:")
            lines.extend(
                f"{pair.entity}.{pair.attribute}: "
                f"{pair.left_source} [{pair.left_territory}] <-> "
                f"{pair.right_source} [{pair.right_territory}]"
                for pair in self.territory_pairs
            )
        return "\n".join(lines)


def _pluralize(entity: str) -> str:
    if entity.endswith(("s", "x", "z", "ch", "sh")):
        return f"{entity}es"
    if len(entity) > 1 and entity.endswith("y") and entity[-2] not in "aeiou":
        return f"{entity[:-1]}ies"
    return f"{entity}s"


def _text(value: Any, label: str, path: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourceContractError(f"{path}: {label} must be a non-empty string")
    return value.strip()


def load_contract(path: Path) -> SourceContract:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise SourceContractError(f"{path}: invalid YAML: {error}") from error
    if not isinstance(raw, dict):
        raise SourceContractError(f"{path}: source contract must be a mapping")

    source = _text(raw.get("source"), "source", path)
    entity = _text(raw.get("into"), "into", path)
    mode = raw.get("mode", "upsert")
    if mode not in {"upsert", "enrich"}:
        raise SourceContractError(f"{path}: mode must be upsert or enrich")

    key = raw.get("key")
    if not isinstance(key, list) or not key or not all(
        isinstance(item, str) and item.strip() for item in key
    ):
        raise SourceContractError(f"{path}: key must be a non-empty list of columns")

    fields = raw.get("fields")
    if not isinstance(fields, dict) or not fields or not all(
        isinstance(attribute, str)
        and attribute.strip()
        and isinstance(column, str)
        and column.strip()
        for attribute, column in fields.items()
    ):
        raise SourceContractError(f"{path}: fields must map attributes to source columns")

    territory = raw.get("territory")
    if territory is not None:
        territory = _text(territory, "territory", path)

    return SourceContract(
        path=path,
        source=source,
        entity=entity,
        key=tuple(item.strip() for item in key),
        mode=mode,
        territory=territory,
        fields={attribute.strip(): column.strip() for attribute, column in fields.items()},
    )


def load_contracts(source_dir: Path) -> tuple[SourceContract, ...]:
    paths = sorted((*source_dir.glob("*.yml"), *source_dir.glob("*.yaml")))
    if not paths:
        raise SourceContractError(f"{source_dir}: no source contracts found")
    return tuple(load_contract(path) for path in paths)


def _topological_order(
    entities: set[str], relationships: list[dict[str, Any]]
) -> tuple[str, ...]:
    children: dict[str, set[str]] = {entity: set() for entity in entities}
    indegree = {entity: 0 for entity in entities}
    for relationship in relationships:
        parent = relationship.get("parent")
        child = relationship.get("child")
        if parent not in entities or child not in entities or parent == child:
            continue
        if child not in children[parent]:
            children[parent].add(child)
            indegree[child] += 1

    ready = [entity for entity, count in indegree.items() if count == 0]
    heapq.heapify(ready)
    ordered: list[str] = []
    while ready:
        parent = heapq.heappop(ready)
        ordered.append(parent)
        for child in sorted(children[parent]):
            indegree[child] -= 1
            if indegree[child] == 0:
                heapq.heappush(ready, child)

    if len(ordered) != len(entities):
        cycle = ", ".join(sorted(entity for entity, count in indegree.items() if count))
        raise SourceContractError(f"relationship cycle among fed entities: {cycle}")
    return tuple(ordered)


def lint_contracts(
    contracts: tuple[SourceContract, ...], model: dict[str, Any]
) -> SourceReport:
    entities = model.get("entities")
    relationships = model.get("relationships")
    if not isinstance(entities, dict) or not isinstance(relationships, list):
        raise SourceContractError("model must contain entities and relationships")

    errors: list[str] = []
    contracts_by_entity: dict[str, list[SourceContract]] = defaultdict(list)
    writers: dict[tuple[str, str], list[SourceContract]] = defaultdict(list)
    for contract in contracts:
        contracts_by_entity[contract.entity].append(contract)
        entity = entities.get(contract.entity)
        if not isinstance(entity, dict):
            errors.append(f"{contract.path}: unknown entity {contract.entity!r}")
            continue
        attributes = {
            item["name"]
            for item in entity.get("attributes", [])
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }
        unknown_fields = sorted(set(contract.fields) - attributes)
        if unknown_fields:
            errors.append(
                f"{contract.path}: unknown {contract.entity} fields: "
                + ", ".join(unknown_fields)
            )
        unmapped_keys = sorted(set(contract.key) - set(contract.fields))
        if unmapped_keys:
            errors.append(
                f"{contract.path}: key columns are not mapped fields: "
                + ", ".join(unmapped_keys)
            )
        for attribute in contract.fields:
            # Enrich keys locate a row; update-only MERGE never writes them.
            if contract.mode == "enrich" and attribute in contract.key:
                continue
            writers[(contract.entity, attribute)].append(contract)

    for entity, entity_contracts in sorted(contracts_by_entity.items()):
        keys = {contract.key for contract in entity_contracts}
        if len(keys) > 1:
            details = "; ".join(
                f"{contract.source}={list(contract.key)}"
                for contract in sorted(entity_contracts, key=lambda item: item.source)
            )
            errors.append(f"{entity}: key mismatch across sources: {details}")

    territory_pairs: list[TerritoryPair] = []
    for (entity, attribute), attribute_writers in sorted(writers.items()):
        for left, right in itertools.combinations(
            sorted(attribute_writers, key=lambda item: item.source), 2
        ):
            if (
                left.mode == "upsert"
                and right.mode == "upsert"
                and left.territory
                and right.territory
            ):
                territory_pairs.append(
                    TerritoryPair(
                        entity,
                        attribute,
                        left.source,
                        left.territory,
                        right.source,
                        right.territory,
                    )
                )
            else:
                errors.append(
                    f"{entity}.{attribute}: writer conflict between "
                    f"{left.source} and {right.source}; both must be upsert sources "
                    "with declared territory"
                )

    if errors:
        raise SourceContractError("\n".join(errors))

    fed_entities = set(contracts_by_entity)
    run_order = _topological_order(fed_entities, relationships)
    ownership = tuple(
        sorted(
            (contract.entity, attribute, contract.source)
            for contract in contracts
            for attribute in contract.fields
            if not (contract.mode == "enrich" and attribute in contract.key)
        )
    )
    return SourceReport(run_order, ownership, tuple(territory_pairs))


def check_sources(
    source_dir: Path = DEFAULT_SOURCES,
    model_path: Path = DEFAULT_MODEL,
    *,
    stream: TextIO | None = None,
) -> SourceReport:
    try:
        model = yaml.safe_load(model_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise SourceContractError(f"{model_path}: invalid YAML: {error}") from error
    if not isinstance(model, dict):
        raise SourceContractError(f"{model_path}: model must be a mapping")
    report = lint_contracts(load_contracts(source_dir), model)
    if stream is None:
        stream = sys.stdout
    print(report.render(), file=stream)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    args = parser.parse_args(argv)
    try:
        check_sources(args.sources, args.model)
    except SourceContractError as error:
        print(f"source contract error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
