# Databricks notebook source
# MAGIC %md
# MAGIC # 01 · Conform one source table
# MAGIC
# MAGIC Conform means rename and check source values against the standard. Valid rows
# MAGIC land in the standard table. Invalid rows go to quarantine with plain-English
# MAGIC reasons; no invalid row is silently dropped or partly inserted.
# MAGIC
# MAGIC Notebook original to this kit. CFIHOS materials © IOGP JIP36, CC BY 4.0.

# COMMAND ----------
# ruff: noqa: E402, F821
import sys
from pathlib import Path

repo_root = Path.cwd().resolve()
if not (repo_root / "src").is_dir():
    repo_root = repo_root.parent
if not (repo_root / "src").is_dir():
    raise FileNotFoundError("run this notebook from the repository Git folder")
sys.path.insert(0, str(repo_root))

from src.identifiers import validate_identifier

dbutils.widgets.text("catalog", "cfihos_demo")
dbutils.widgets.text("yaml_file", "src/conform/sources/demo_plants.yml")

catalog = validate_identifier(dbutils.widgets.get("catalog").strip())
yaml_file = Path(dbutils.widgets.get("yaml_file").strip())
if not yaml_file.is_absolute():
    yaml_file = repo_root / yaml_file
model_file = repo_root / "model" / "model.yml"

# COMMAND ----------
# MAGIC %md
# MAGIC ## What the five YAML parts mean
# MAGIC
# MAGIC 1. `from` names the governed source table, while `source` gives the mapping a name.
# MAGIC 2. `into` names the standard entity that receives valid rows.
# MAGIC 3. `fields` pairs each standard attribute with one source column.
# MAGIC 4. `value_maps` translates source codes into the standard's values.
# MAGIC 5. `key` identifies reruns; `mode` and optional `territory` control writes.

# COMMAND ----------
# MAGIC %md
# MAGIC ## Validate first, then run
# MAGIC
# MAGIC Validation stops unknown entities, attributes, keys, and YAML options before
# MAGIC any source row can be written.

# COMMAND ----------
from src.conform import conform, validate_source_config

source_config = validate_source_config(yaml_file, model_file)
display(
    spark.createDataFrame(
        [(source_config.source, source_config.into, str(yaml_file))],
        "source string, entity string, validated_yaml string",
    )
)

# COMMAND ----------
summary = conform(spark, catalog, yaml_file, model_file)
display(
    spark.createDataFrame(
        [(summary["landed"], summary["quarantined"])],
        "landed long, quarantined long",
    )
)

# COMMAND ----------
# MAGIC %md
# MAGIC ## Quarantine details
# MAGIC
# MAGIC These are the rows for this source and entity that could not land. Read the
# MAGIC `reasons` array, correct the source or mapping, and rerun safely.

# COMMAND ----------
from pyspark.sql import functions as F

display(
    spark.table(f"{catalog}.cfihos_quarantine.rows")
    .where(
        (F.col("source") == source_config.source)
        & (F.col("entity") == source_config.into)
    )
    .select(
        "source",
        "entity",
        "source_key",
        "source_row_json",
        "reasons",
        "quarantined_at",
    )
    .orderBy(F.col("quarantined_at").desc())
)
