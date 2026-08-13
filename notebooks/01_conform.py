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
# MAGIC %pip install PyYAML==6.0.2

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

if "catalog" not in dbutils.widgets.getAll():
    dbutils.widgets.text("catalog", "cfihos_demo")
if "yaml_file" not in dbutils.widgets.getAll():
    dbutils.widgets.text("yaml_file", "src/conform/sources/demo_plants.yml")

# COMMAND ----------

def read_parameters():
    selected_catalog = validate_identifier(dbutils.widgets.get("catalog").strip())
    yaml_value = dbutils.widgets.get("yaml_file").strip()
    if not yaml_value:
        raise ValueError("yaml_file must not be empty")
    selected_yaml = Path(yaml_value)
    if selected_yaml.suffix.lower() not in {".yml", ".yaml"}:
        raise ValueError("yaml_file must end in .yml or .yaml")
    if not selected_yaml.is_absolute():
        selected_yaml = repo_root / selected_yaml
    return selected_catalog, selected_yaml, repo_root / "model" / "model.yml"

# COMMAND ----------
# MAGIC %md
# MAGIC ## Choose the source mapping
# MAGIC
# MAGIC Set both widgets before continuing. Use the exact same catalog as notebook 00.
# MAGIC Change `yaml_file` for each source, following the parent-first order printed by
# MAGIC `tests/check_sources.py`.

# COMMAND ----------
catalog, yaml_file, model_file = read_parameters()
display(
    spark.createDataFrame(
        [(catalog, str(yaml_file))],
        "selected_catalog string, selected_yaml string",
    )
)

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
from src.conform import conform, entity_metadata, load_model, validate_source_config

catalog, yaml_file, model_file = read_parameters()
source_config = validate_source_config(yaml_file, model_file)
metadata = entity_metadata(load_model(model_file), source_config.into)
target_table = f"{catalog}.cfihos_{metadata.subject_area}.{metadata.name}"
display(
    spark.createDataFrame(
        [(source_config.source, source_config.into, str(yaml_file), target_table)],
        "source string, entity string, validated_yaml string, target_table string",
    )
)

# COMMAND ----------
catalog, yaml_file, model_file = read_parameters()
source_config = validate_source_config(yaml_file, model_file)
metadata = entity_metadata(load_model(model_file), source_config.into)
target_table = f"{catalog}.cfihos_{metadata.subject_area}.{metadata.name}"
summary = conform(spark, catalog, yaml_file, model_file)
persisted_rows = spark.table(target_table).count()
display(
    spark.createDataFrame(
        [(summary["landed"], summary["quarantined"], target_table, persisted_rows)],
        (
            "valid_rows_this_run long, invalid_rows_this_run long, "
            "target_table string, persisted_rows_after_run long"
        ),
    )
)

# COMMAND ----------
display(spark.table(target_table).limit(100))

# COMMAND ----------
# MAGIC %md
# MAGIC ## Quarantine history
# MAGIC
# MAGIC This is retained rejection history for this source and entity, not only the
# MAGIC latest run. `run_id` identifies the run that first recorded each exact
# MAGIC rejection. Read `reasons`, correct the source or mapping, and rerun safely.

# COMMAND ----------
from pyspark.sql import functions as F

catalog, yaml_file, model_file = read_parameters()
source_config = validate_source_config(yaml_file, model_file)
display(
    spark.table(f"{catalog}.cfihos_quarantine.rows")
    .where(
        (F.col("source") == source_config.source)
        & (F.col("entity") == source_config.into)
    )
    .select(
        "source",
        "entity",
        "run_id",
        "source_key",
        "source_row_json",
        "reasons",
        "quarantined_at",
    )
    .orderBy(F.col("quarantined_at").desc())
    .limit(100)
)
