# Databricks notebook source
# MAGIC %md
# MAGIC # 00 · Get started
# MAGIC
# MAGIC This creates the standard's tables, empty, with definitions attached. It also
# MAGIC loads the standard's official vocabulary into lookup tables. The tables start
# MAGIC empty because CFIHOS supplies the structure and vocabulary, not your asset
# MAGIC records. Use a fresh catalog for the walkthrough.
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
catalog = validate_identifier(dbutils.widgets.get("catalog").strip())

# COMMAND ----------
# MAGIC %md
# MAGIC ## Create the standard's empty tables
# MAGIC
# MAGIC If `CREATE CATALOG` is forbidden in your workspace, ask an administrator to
# MAGIC pre-create the catalog named above, then rerun this cell. The deployer detects
# MAGIC an existing catalog and continues inside it.

# COMMAND ----------
from src.deploy_foundation import deploy

deploy(spark, repo_root, catalog)

# COMMAND ----------
# MAGIC %md
# MAGIC ## Load the standard's vocabulary
# MAGIC
# MAGIC The Core Reference Data Library (RDL) supplies the standard class, property,
# MAGIC unit, document, and discipline values. The loader keeps a reconciliation audit
# MAGIC and records explained duplicate rows instead of dropping them silently.

# COMMAND ----------
from src.load_rdl import load_rdl

load_rdl(spark, repo_root / "spec" / "rdl", catalog, "2.0")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Prove both pieces are queryable
# MAGIC
# MAGIC The first result describes the empty `tag` table, including its definitions.
# MAGIC The second shows five official equipment-class vocabulary rows.

# COMMAND ----------
display(spark.sql(f"DESCRIBE TABLE {catalog}.cfihos_functional_asset.tag"))

# COMMAND ----------
display(
    spark.sql(
        f"""SELECT equipment_class_cfihos_unique_code, equipment_class_name
        FROM {catalog}.cfihos_ref.equipment_class
        WHERE rdl_version = '2.0'
        ORDER BY equipment_class_name
        LIMIT 5"""
    )
)

# COMMAND ----------
# MAGIC %md
# MAGIC The empty standard tables and the vocabulary are ready. In Catalog Explorer,
# MAGIC create the `bronze` schema and use **Create table from file** for the demo CSVs
# MAGIC under `tutorial/`. Then open `01_conform.py`.
