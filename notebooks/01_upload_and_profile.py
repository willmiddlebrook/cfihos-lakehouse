# Databricks notebook source
# ruff: noqa: E402, F821
# MAGIC %md
# MAGIC # 01 · Upload and profile a source
# MAGIC
# MAGIC Drag a CSV into the `uploads` volume with Catalog Explorer. This notebook is
# MAGIC the governed file-to-table convenience layer; the source-loading engine consumes
# MAGIC Delta **tables** (governed tables with reliable history). See
# MAGIC [how the system works](../docs/HOW-IT-WORKS.md) for the four-step loop and
# MAGIC plain-language glossary.
# MAGIC
# MAGIC `source_name` names one logical source and stays `example_cmms` for both
# MAGIC tutorial files. `feed_table_name` names the individual bronze input table. Use
# MAGIC the neutral files under `tutorial/` and repeat this notebook once per feed.
# MAGIC
# MAGIC Notebook original to this kit. CFIHOS materials © IOGP JIP36, CC BY 4.0.

# COMMAND ----------
import os
import sys
from pathlib import Path

repo_root = Path(os.path.abspath(".."))
sys.path.insert(0, os.path.abspath(".."))

from src.identifiers import validate_identifier

dbutils.widgets.text("catalog", "cfihos_tutorial")
dbutils.widgets.text("source_name", "example_cmms")
dbutils.widgets.text("feed_table_name", "example_locations")
dbutils.widgets.text("file_name", "example_locations.csv")
dbutils.widgets.dropdown("overwrite", "false", ["false", "true"])

catalog = dbutils.widgets.get("catalog").strip()
source_name = dbutils.widgets.get("source_name").strip()
feed_table_name = dbutils.widgets.get("feed_table_name").strip()
file_name = dbutils.widgets.get("file_name").strip()
overwrite = dbutils.widgets.get("overwrite").strip().casefold()
validate_identifier(catalog)
validate_identifier(source_name)
validate_identifier(feed_table_name)
if not file_name or Path(file_name).name != file_name:
    raise ValueError("file_name must name one file in the uploads volume")
if overwrite not in {"false", "true"}:
    raise ValueError("overwrite must be false or true")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Check the upload
# MAGIC
# MAGIC Upload the named file through Catalog Explorer, then rerun this cell to confirm
# MAGIC that it is in the throwaway catalog's governed volume.

# COMMAND ----------
volume_path = f"/Volumes/{catalog}/cfihos_onramp/uploads"
display(dbutils.fs.ls(volume_path))

# COMMAND ----------
# MAGIC %md
# MAGIC ## Materialize the CSV as a bronze table
# MAGIC
# MAGIC The guard below refuses to replace an existing table unless `overwrite` is
# MAGIC explicitly set to `true`; reruns never clobber data silently.

# COMMAND ----------
table_name = f"{catalog}.bronze.{feed_table_name}"
if spark.catalog.tableExists(table_name) and overwrite != "true":
    raise ValueError(f"{table_name} already exists; set overwrite=true to replace it")

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.bronze")
file_path = f"{volume_path}/{file_name}".replace("'", "''")
spark.sql(
    f"""CREATE OR REPLACE TABLE {table_name} AS
    SELECT * FROM read_files('{file_path}', format => 'csv', header => true)"""
)

display(spark.table(table_name).selectExpr("count(*) AS rows"))
display(spark.sql(f"DESCRIBE TABLE {table_name}"))

# COMMAND ----------
# MAGIC %md
# MAGIC ## Profile the governed table
# MAGIC
# MAGIC A source profile summarizes columns, null rates, distinct counts, and sample
# MAGIC values before anyone maps them. It includes deterministic samples and, for
# MAGIC small domains, complete distinct-value lists. It therefore contains raw source
# MAGIC values and must be treated as data.

# COMMAND ----------
from src.onramp.profile_source import profile_source

profile_yaml = profile_source(spark, catalog, source_name, table_name)
print(profile_yaml)

# COMMAND ----------
# MAGIC %md
# MAGIC For the tutorial, upload both files under `tutorial/`. Run this notebook with
# MAGIC the defaults first, then repeat it with `feed_table_name=example_assets` and
# MAGIC `file_name=example_assets.csv`, keeping `source_name=example_cmms`. Open notebook
# MAGIC 02 only after both bronze tables exist.
# MAGIC
# MAGIC In implementation mode, commit the printed profile as
# MAGIC `src/onramp/profiles/<source>.yml` in your fork. Keep a sensitive profile out
# MAGIC of Git and pin the proposal to its controlled local copy. In evaluation mode,
# MAGIC you can proceed with the disposable tutorial profiles.
