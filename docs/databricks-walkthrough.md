# Run the CSV walkthrough in Databricks

This is the click-by-click path for a new Git folder. It was last verified on
Databricks serverless compute on 2026-08-13.

## Before you start

You need a Unity Catalog-enabled workspace and a catalog for the test. If the
catalog already exists, you need `USE CATALOG` and `CREATE SCHEMA`. You also need
permission to create the three `bronze` tables. Use a fresh catalog when you want
the exact acceptance totals below.

Create a Databricks Git folder from:

```text
https://github.com/willmiddlebrook/cfihos-lakehouse.git
```

Open files from that Git folder. The notebooks use nearby `src/`, `model/`, and
`spec/` files, so copying a notebook by itself is not supported.

## 1. Create the empty standard tables and load the vocabulary

1. Open `notebooks/00_get_started.py`.
2. Run its first Python setup cell once. This creates the `catalog` widget; it
   does not deploy anything.
3. Set `catalog` to the catalog you will use for every step.
4. Run the full notebook. The setup cell preserves the value you selected.
5. Confirm every cell succeeds. The asset tables are intentionally empty. The
   Core Reference Data Library (RDL) lookup tables are populated.

This query proves that the 21 committed official RDL files reconciled completely:

```sql
SELECT
  count(*) AS rdl_files,
  sum(source_rows) AS source_rows,
  sum(loaded_rows) AS loaded_rows,
  sum(exception_rows) AS explained_exception_rows
FROM <catalog>.cfihos_ref.load_audit
WHERE rdl_version = '2.0';
```

The exact result is `21 / 43753 / 42472 / 1281`. Loaded rows plus explained
duplicate exceptions equals every source row.

## 2. Upload the three CSV files

In Catalog Explorer, create or select `<catalog>.bronze`. Use **Create table from
file** for each file under `tutorial/` and keep every input column as `STRING`:

| File | Target table | Rows |
|---|---|---:|
| `demo_plants.csv` | `<catalog>.bronze.demo_plants` | 1 |
| `demo_process_units.csv` | `<catalog>.bronze.demo_process_units` | 2 |
| `demo_tags.csv` | `<catalog>.bronze.demo_tags` | 8 |

Check the upload before conforming:

```sql
SELECT
  (SELECT count(*) FROM <catalog>.bronze.demo_plants) AS demo_plants,
  (SELECT count(*) FROM <catalog>.bronze.demo_process_units) AS demo_process_units,
  (SELECT count(*) FROM <catalog>.bronze.demo_tags) AS demo_tags;
```

The result must be `1 / 2 / 8`.

## 3. Conform each table in parent-first order

1. Open `notebooks/01_conform.py`.
2. Run the `%pip` cell, then the Python setup cell once. These install the pinned
   YAML reader and create the `catalog` and `yaml_file` widgets.
3. Set `catalog` to the exact same value used in notebook 00.
4. Set `yaml_file` to `src/conform/sources/demo_plants.yml` and run the notebook.
5. Run it again with `src/conform/sources/demo_process_units.yml`.
6. Run it again with `src/conform/sources/demo_tags.yml`.

The order matters because a process unit refers to a plant, and a tag refers to
a process unit. Each run displays rows checked in that run, the resolved target
table, the total persisted rows, up to 100 target rows, and retained quarantine
history.

## 4. Prove the result and the safe rerun

Run:

```sql
SELECT
  (SELECT count(*) FROM <catalog>.cfihos_functional_asset.plant) AS plants,
  (SELECT count(*) FROM <catalog>.cfihos_functional_asset.process_unit) AS process_units,
  (SELECT count(*) FROM <catalog>.cfihos_functional_asset.tag) AS tags,
  (SELECT count(*) FROM <catalog>.cfihos_quarantine.rows) AS quarantined;
```

The exact result is `1 / 2 / 6 / 2`. The other two tag rows are retained in
quarantine. Prove their reasons with:

```sql
SELECT reason, count(*) AS records
FROM (
  SELECT explode(reasons) AS reason
  FROM <catalog>.cfihos_quarantine.rows
)
GROUP BY reason
ORDER BY reason;
```

Each of these occurs once:

- `process_unit_code is required and missing`
- `WIDGET is not a valid tag class`

Now run the same three YAML files again in the same order. The result must remain
`1 / 2 / 6 / 2`, with the same two quarantine rows. That proves the target MERGE
and quarantine recording are safe to rerun.

## Troubleshooting the first run

- `PERMISSION_DENIED` while creating a catalog: use a catalog an administrator
  has created and ask for `USE CATALOG` and `CREATE SCHEMA`.
- `ModuleNotFoundError: yaml`: pull the latest repository revision. Notebook 01
  must contain the pinned `PyYAML==6.0.2` `%pip` cell.
- A different catalog appears in notebook 01: reset its `catalog` widget to the
  exact value from notebook 00. Widget values do not carry between notebooks.
- For a Git-backed Jobs API task, omit the `.py` suffix: use
  `notebooks/00_get_started` or `notebooks/01_conform`. In the Git folder UI,
  continue opening the visible `.py` files normally.

The notebooks write tables to Unity Catalog. They do not push anything to Git.
Editing a YAML file changes only your Databricks Git folder until you explicitly
commit and push it.
