"""Apply explicit per-attribute source precedence without arbitrary tie breaking."""

from __future__ import annotations

import argparse
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Resolution:
    winner: dict[str, Any] | None
    conflicts: tuple[dict[str, Any], ...]


def resolve_claims(
    claims: Iterable[dict[str, Any]],
    *,
    current_winner: dict[str, Any] | None = None,
) -> Resolution:
    """Resolve incoming claims against the still-current published winner.

    A new observation supersedes the same source's prior observation. A winner
    from another source remains a candidate, so processing sources in separate
    runs cannot make arrival order override the configured precedence.
    """
    values = list(claims)
    if current_winner is not None:
        current = {
            **current_winner,
            "source_system": current_winner.get(
                "source_system", current_winner.get("winning_source")
            ),
        }
        if current["source_system"] is None:
            raise KeyError("current_winner requires winning_source or source_system")
        if not any(
            item["source_system"] == current["source_system"] for item in values
        ):
            values.append(current)
    if not values:
        return Resolution(None, ())
    best_rank = min(int(item["wins_rank"]) for item in values)
    leaders = [item for item in values if int(item["wins_rank"]) == best_rank]
    if len(leaders) != 1:
        return Resolution(
            None,
            tuple({**item, "conflict_type": "tied_rank"} for item in values),
        )
    winner = leaders[0]
    conflicts = tuple(
        {**item, "conflict_type": "losing_claim", "winning_source": winner["source_system"]}
        for item in values
        if item is not winner and item.get("value") != winner.get("value")
    )
    return Resolution(winner, conflicts)


def resolve_all(
    claims: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for claim in claims:
        grouped[(claim["entity"], claim["spine_id"], claim["attribute"])].append(claim)
    winners, conflicts = [], []
    for group in grouped.values():
        result = resolve_claims(group)
        if result.winner is not None:
            winners.append(result.winner)
        conflicts.extend(result.conflicts)
    return winners, conflicts


def publish_claims(spark: Any, catalog: str, run_id: str) -> None:
    from pyspark.sql import Window
    from pyspark.sql import functions as F

    claim_columns = [
        "run_id",
        "source_system",
        "entity",
        "spine_id",
        "attribute",
        "value",
        "wins_rank",
    ]
    keys = ["entity", "spine_id", "attribute"]
    claims = (
        spark.table(f"{catalog}.cfihos_onramp.staged_claims")
        .filter(F.col("run_id") == run_id)
        .select(*claim_columns)
    )

    # One engine run normally contains one source. Bring the published winner
    # for every touched attribute into this run's candidate set so arrival order
    # cannot override precedence. An incoming observation replaces that same
    # source's old observation instead of tying with its own history.
    current_published = spark.table(
        f"{catalog}.cfihos_trust.published_attributes"
    ).filter(F.col("is_current"))
    touched_attributes = claims.select(*keys).distinct()
    incoming_sources = claims.select(*keys, "source_system").distinct()
    current_candidates = (
        current_published.join(touched_attributes, keys, "inner")
        .select(
            F.lit(run_id).alias("run_id"),
            F.col("winning_source").alias("source_system"),
            *keys,
            "value",
            "wins_rank",
        )
        .join(incoming_sources, [*keys, "source_system"], "left_anti")
    )
    candidates = claims.unionByName(current_candidates)

    group = Window.partitionBy("entity", "spine_id", "attribute")
    ranked = candidates.withColumn(
        "best_rank", F.min("wins_rank").over(group)
    ).withColumn(
        "leader_count",
        F.sum(F.when(F.col("wins_rank") == F.col("best_rank"), 1).otherwise(0)).over(group),
    )
    winners = ranked.filter(
        (F.col("wins_rank") == F.col("best_rank")) & (F.col("leader_count") == 1)
    ).select(
        "entity",
        "spine_id",
        "attribute",
        "value",
        F.col("source_system").alias("winning_source"),
        "wins_rank",
    )
    conflict_rows = ranked.join(
        winners.select(
            "entity",
            "spine_id",
            "attribute",
            F.col("winning_source"),
            F.col("value").alias("winning_value"),
        ),
        ["entity", "spine_id", "attribute"],
        "left",
    ).filter(
        (F.col("leader_count") > 1)
        | ~F.col("value").eqNullSafe(F.col("winning_value"))
    )
    conflicts = conflict_rows.select(
        F.sha2(
            F.concat_ws(
                "|", "run_id", "entity", "spine_id", "attribute", "source_system", "value"
            ),
            256,
        ).alias("conflict_id"),
        "run_id",
        "entity",
        "spine_id",
        "attribute",
        F.when(F.col("leader_count") > 1, "tied_rank")
        .otherwise("losing_claim")
        .alias("conflict_type"),
        "source_system",
        "value",
        "wins_rank",
        "winning_source",
        "winning_value",
        F.current_timestamp().alias("recorded_at"),
    )
    conflicts.write.mode("append").saveAsTable(f"{catalog}.cfihos_trust.attribute_conflicts")

    winners.createOrReplaceTempView("cfihos_winning_claims")
    spark.sql(
        f"""MERGE INTO {catalog}.cfihos_trust.published_attributes target
        USING cfihos_winning_claims source
        ON target.entity = source.entity
          AND target.spine_id = source.spine_id
          AND target.attribute = source.attribute
          AND target.is_current = true
        WHEN MATCHED AND (
          NOT (target.value <=> source.value)
          OR target.winning_source <> source.winning_source
          OR target.wins_rank <> source.wins_rank
        ) THEN UPDATE SET
          target.valid_to = current_timestamp(), target.is_current = false"""
    )
    current = spark.table(f"{catalog}.cfihos_trust.published_attributes").filter(
        F.col("is_current")
    )
    same_current_winner = (
        (winners.entity == current.entity)
        & (winners.spine_id == current.spine_id)
        & (winners.attribute == current.attribute)
        & winners.value.eqNullSafe(current.value)
        & (winners.winning_source == current.winning_source)
        & (winners.wins_rank == current.wins_rank)
    )
    additions = winners.join(current, same_current_winner, "left_anti").select(
        winners["entity"],
        winners["spine_id"],
        winners["attribute"],
        winners["value"],
        winners["winning_source"],
        winners["wins_rank"],
        F.current_timestamp().alias("valid_from"),
        F.lit(None).cast("timestamp").alias("valid_to"),
        F.lit(True).alias("is_current"),
    )
    additions.write.mode("append").saveAsTable(f"{catalog}.cfihos_trust.published_attributes")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    from pyspark.sql import SparkSession

    publish_claims(SparkSession.builder.getOrCreate(), args.catalog, args.run_id)
    return 0


if __name__ == "__main__":
    main()
