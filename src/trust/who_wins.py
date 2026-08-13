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


def resolve_claims(claims: Iterable[dict[str, Any]]) -> Resolution:
    values = list(claims)
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

    claims = spark.table(f"{catalog}.cfihos_onramp.staged_claims").filter(
        F.col("run_id") == run_id
    )
    group = Window.partitionBy("entity", "spine_id", "attribute")
    ranked = claims.withColumn("best_rank", F.min("wins_rank").over(group)).withColumn(
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
    ).filter((F.col("leader_count") > 1) | (F.col("value") != F.col("winning_value")))
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
        WHEN MATCHED AND NOT target.value <=> source.value THEN UPDATE SET
          target.valid_to = current_timestamp(), target.is_current = false"""
    )
    current = spark.table(f"{catalog}.cfihos_trust.published_attributes").filter(
        F.col("is_current")
    )
    additions = winners.join(
        current,
        ["entity", "spine_id", "attribute", "value"],
        "left_anti",
    ).select(
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
    raise SystemExit(main())
