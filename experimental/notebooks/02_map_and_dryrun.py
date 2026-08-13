# Databricks notebook source
# ruff: noqa: E402, F821
# MAGIC %md
# MAGIC # 02 · Map the source and preview the three buckets
# MAGIC
# MAGIC Start with [how the system works](../docs/HOW-IT-WORKS.md). A mapping is the
# MAGIC small YAML configuration that lines up source columns and codes with the
# MAGIC standard. Every eligible row ends in one of three plain buckets: **link** to an
# MAGIC asset already present / **create** an asset when this is the founding source /
# MAGIC **not sure** and send it to a human.
# MAGIC
# MAGIC Copy the neutral example YAML and edit its `fields` (column renames),
# MAGIC `value_maps` (code translations), `match_on` (same-asset keys), and `wins_rank`
# MAGIC (source precedence) against the source profile. Point each `feeds.*.from` value
# MAGIC at the bronze table—the governed raw-source table—created in notebook 01.
# MAGIC Tutorial edits can stay uncommitted; implementation edits move through the
# MAGIC pull-request workflow in `docs/mapping-proposals.md`.
# MAGIC
# MAGIC Notebook original to this kit. CFIHOS materials © IOGP JIP36, CC BY 4.0.

# COMMAND ----------
import json
import os
import sys
from pathlib import Path

import yaml

repo_root = Path(os.path.abspath(".."))
sys.path.insert(0, os.path.abspath(".."))

from src.identifiers import validate_identifier

dbutils.widgets.text("catalog", "cfihos_tutorial")
dbutils.widgets.text("source_config", "src/onramp/sources/example_cmms.yml")
dbutils.widgets.dropdown("run_live", "false", ["false", "true"])

catalog = dbutils.widgets.get("catalog").strip()
source_config = dbutils.widgets.get("source_config").strip()
run_live = dbutils.widgets.get("run_live").strip().casefold()
validate_identifier(catalog)
if run_live not in {"false", "true"}:
    raise ValueError("run_live must be false or true")

config_path = Path(source_config)
if not config_path.is_absolute():
    config_path = repo_root / config_path
config_path = config_path.resolve()
try:
    config_path.relative_to(repo_root.resolve())
except ValueError as error:
    raise ValueError("source_config must resolve inside this Git folder") from error
if not config_path.is_file():
    raise FileNotFoundError(config_path)

# COMMAND ----------
# MAGIC %md
# MAGIC ## Contract gate
# MAGIC
# MAGIC This is the same canonical model and source contract used by the job. Every
# MAGIC error and every verified-or-acknowledged target warning is shown without a
# MAGIC fallback. Errors stop the notebook before it can query source tables.

# COMMAND ----------
from src.onramp.config_contract import validate_value_map_targets
from src.onramp.engine import load_yaml, validate_config

raw_config = config_path.read_text(encoding="utf-8").replace("${catalog}", catalog)
config = yaml.safe_load(raw_config)
if not isinstance(config, dict):
    raise ValueError(f"{config_path} must contain a YAML mapping")
model = load_yaml(repo_root / "model" / "model.yml")

errors = list(validate_config(config, model))
target_contract = validate_value_map_targets(config, model, repo_root / "spec" / "rdl")
warnings = [warning.as_dict() for warning in target_contract.warnings]

gate_messages = [("error", message) for message in errors]
gate_messages.extend(
    ("warning", json.dumps(warning, sort_keys=True)) for warning in warnings
)
if gate_messages:
    display(spark.createDataFrame(gate_messages, "severity string, message string"))
    for severity, message in gate_messages:
        print(f"{severity}: {message}")
else:
    print("Source config contract valid with no warnings.")
if errors:
    raise ValueError("invalid source config:\n- " + "\n- ".join(errors))

# COMMAND ----------
# MAGIC %md
# MAGIC ## Source-table preflight
# MAGIC
# MAGIC Every configured feed table must exist before the shared engine starts. The
# MAGIC tutorial config requires both `example_locations` and `example_assets`; run
# MAGIC notebook 01 once for each neutral CSV under `tutorial/`.

# COMMAND ----------
table_checks = [
    (entity_name, feed["from"], spark.catalog.tableExists(feed["from"]))
    for entity_name, feed in config["feeds"].items()
]
display(
    spark.createDataFrame(
        table_checks, "entity string, configured_table string, exists boolean"
    ).orderBy("entity")
)
missing_tables = [table_name for _, table_name, exists in table_checks if not exists]
if missing_tables:
    raise FileNotFoundError(
        "Missing configured source tables; run notebook 01 once per feed:\n- "
        + "\n- ".join(missing_tables)
    )

# COMMAND ----------
# MAGIC %md
# MAGIC ## Optional proposal gate
# MAGIC
# MAGIC A checked-in proposal is validated against its candidate YAML, pinned model,
# MAGIC profile, and RDL evidence. A tutorial config with no proposal follows the
# MAGIC explicitly human-authored path.

# COMMAND ----------
from src.onramp.validate_proposal import validate_proposal

source = config["source"]
proposal_path = repo_root / "src" / "onramp" / "proposals" / f"{source}.proposal.yml"
candidate_path = config_path
if proposal_path.exists():
    proposal_errors = validate_proposal(proposal_path, candidate_path, repo_root)
    if proposal_errors:
        display(
            spark.createDataFrame(
                [(message,) for message in proposal_errors], "proposal_error string"
            )
        )
        raise ValueError("invalid mapping proposal:\n- " + "\n- ".join(proposal_errors))
    print(f"Mapping proposal valid: {proposal_path.relative_to(repo_root)}")
else:
    print("No proposal found; continuing on the human-authored tutorial path.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Predict the live outcome without writing
# MAGIC
# MAGIC A dry run executes the job's decision logic with zero writes. The summary shows
# MAGIC rows already linked, linked exactly, linked after safe normalization,
# MAGIC `would_found` (would be created by the founding source), blocked by an
# MAGIC untranslated code, or queued as “not sure.” For a later source against an
# MAGIC empty registry, every eligible row queues; blocked rows are excluded, so when
# MAGIC nothing matched, `queued + blocked_rows == input_rows`. Blocked rows are
# MAGIC findings to resolve, not records to hide.

# COMMAND ----------
from src.onramp.engine import run_spark

report = run_spark(spark, catalog, config, model, dry_run=True)
summary_rows = []
unmapped_rows = []
for entity_name, entity_report in report["entities"].items():
    summary_rows.append(
        (
            entity_name,
            entity_report["input_rows"],
            entity_report["blocked_rows"],
            entity_report["already_mapped"],
            entity_report["exact"],
            entity_report["normalized"],
            entity_report["would_found"],
            entity_report["queued"],
            entity_report["coverage"],
        )
    )
    unmapped_rows.extend(
        (
            entity_name,
            item["key"],
            item["source_value"],
            item["rows"],
        )
        for item in entity_report["unmapped_codes"]
    )

display(
    spark.createDataFrame(
        summary_rows,
        "entity string, input_rows long, blocked_rows long, already_mapped long, "
        "exact long, normalized long, would_found long, queued long, coverage double",
    ).orderBy("entity")
)
display(
    spark.createDataFrame(
        unmapped_rows,
        "entity string, key string, source_value string, rows long",
    ).orderBy("entity", "key", "source_value")
)
print(json.dumps(report, indent=2, default=str))

# COMMAND ----------
# MAGIC %md
# MAGIC ## Optional live run
# MAGIC
# MAGIC Set `run_live=true` only after reviewing the report. A live run writes source
# MAGIC configuration, identity, claim, review, and exception state. That is safe in a
# MAGIC throwaway catalog; an implementation run requires an approved, committed YAML.
# MAGIC A **founding source** is the one first-census system allowed to create the
# MAGIC initial asset list. It must explicitly declare `origination: founding`; only
# MAGIC one committed source may hold that role.

# COMMAND ----------
from src.onramp.engine import _sync_config

if run_live == "true":
    _sync_config(spark, catalog, config, raw_config)
    live_report = run_spark(spark, catalog, config, model, dry_run=False)
    print(f"run_id={live_report['run_id']}")
else:
    print("Dry-run only. Set run_live=true and rerun this cell to write the reviewed outcome.")

# COMMAND ----------
# MAGIC %md
# MAGIC A live **founding** source creates golden records; later sources map to that
# MAGIC registry or enter its explicit gray-zone surfaces. Next, open `03_health.py`
# MAGIC to inspect the living registry and `04_steward.py` to work its review queue.
