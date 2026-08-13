# CFIHOS Lakehouse Kit

## What this kit does

This repo compiles and enforces the CFIHOS v2.0 standard
(https://www.jip36-cfihos.org/cfihos-standards/). From the standard's own
pinned files (spec/C-DM-002 dictionary XLSX + 21 Core RDL CSVs) it produces,
in a Unity Catalog catalog: the standard's tables with the standard's
definitions as column comments; required fields enforced with real NOT NULL;
the vocabulary loaded as queryable lookup tables in cfihos_ref; and a conform
step that lands valid rows in the model and quarantines invalid rows with
plain-English reasons. The standard, compiled and enforced — nothing else.

In plain language: deploy the empty standard tables, load the standard's vocabulary,
then use a small YAML file to say how each source table maps to them. Valid rows land
in the CFIHOS tables. Invalid rows stay visible in a quarantine table with reasons you
can act on.

The result is CFIHOS v2.0-aligned. It is not CFIHOS certified and is not part of the
formal CFIHOS conformance program.

## 15-minute quickstart in Databricks

You need a Unity Catalog-enabled Databricks workspace, permission to use or create a
catalog, and serverless compute. This walkthrough uses a fresh catalog so it cannot
mix demo rows with real data.

1. In your Databricks workspace, choose **Workspace > Create > Git folder** and clone
   this repository. Open `notebooks/00_get_started.py` from that Git folder.
2. Enter a lowercase catalog name such as `cfihos_demo_user` and run notebook 00.
   It creates the standard's empty tables, loads the Core Reference Data Library
   (RDL), and displays proof that both are queryable. If you cannot create catalogs,
   ask an administrator to pre-create that catalog and rerun the notebook.
3. In Catalog Explorer, create a schema named `bronze` in that catalog. Use **Create
   table from file** to upload the three CSVs in `tutorial/`. Keep the filenames as
   table names: `demo_plants`, `demo_process_units`, and `demo_tags`.
4. The matching YAML files are in `src/conform/sources/`. Copy a demo YAML when you
   want your own editable mapping; the checked-in copies already match these demo
   tables. Open `notebooks/01_conform.py` and set `yaml_file` first to
   `src/conform/sources/demo_plants.yml`.
5. Run notebook 01 three times in this order: `demo_plants.yml`,
   `demo_process_units.yml`, then `demo_tags.yml`. Each run validates the YAML before
   writing, shows how many rows landed or were quarantined, and displays the reasons.

The notebooks write to the chosen catalog, not to Git. Copying or editing a YAML
changes only your Git folder until you explicitly commit and push it.

The YAML is the whole source-specific contract. `from` names the governed source
table. `into` names the standard entity. `fields` maps standard attributes to source
columns. `value_maps` translates source codes into standard values. `key` tells the
MERGE which row to update on a rerun.

## Demo fixture CSVs

These are the exact files under `tutorial/`.

`demo_plants.csv`:

```csv
plant_code,plant_name
P-004,Compressor Station 4
```

`demo_process_units.csv`:

```csv
plant_code,process_unit_code,process_unit_name
P-004,U-100,Inlet Separation
P-004,U-200,Compression
```

`demo_tags.csv`:

```csv
plant_code,tag_name,tag_description,process_unit_code,tag_class_code,tag_status_code,designed_by_company_name,production_critical,safety_critical
P-004,T-001,Inlet separator,U-100,SEP,IN_SVC,Demo Design Office,Y,N
P-004,T-002,Suction knock out drum,U-100,KOD,IN_SVC,Demo Design Office,Y,Y
P-004,T-003,Suction pressure transmitter,U-100,PT,IN_SVC,Demo Design Office,N,Y
P-004,T-004,Main lube oil pump,U-200,PUMP_C,IN_SVC,Demo Design Office,Y,N
P-004,T-005,Standby lube oil pump,U-200,PUMP_C,STANDBY,Demo Design Office,N,N
P-004,T-006,Recycle control valve,U-200,CV,IN_SVC,Demo Design Office,Y,Y
P-004,T-007,Discharge flow transmitter,,FT,IN_SVC,Demo Design Office,N,N
P-004,T-008,Unsupported demo class,U-200,WIDGET,IN_SVC,Demo Design Office,N,N
```

`T-007` and `T-008` are deliberately invalid. They prove that a row is never silently
dropped or partly inserted.

## Acceptance result

Against a fresh catalog, the demo must produce exactly this result:

The automated acceptance runner refuses to overwrite existing demo inputs or non-empty
core tables.

| Check | Exact result |
|---|---:|
| Plants landed | 1 |
| Process units landed | 2 |
| Tags landed | 6 |
| Rows quarantined | 2 |

The two quarantine reasons are exactly:

- `process_unit_code is required and missing`
- `WIDGET is not a valid tag class`

Run all three YAMLs a second time. The landed and quarantined counts must not change;
MERGE makes the conform step safe to rerun.

## Adding more sources over time

Every source maps to the model, never to another source. Classify each new YAML:

1. Feeds a new entity: run it after its parents. `tests/check_sources.py` prints the
   order; a missing parent is quarantined with a plain reason.
2. Same entity, different rows: use the identical `key` and declare `territory`.
3. Same rows, different columns: use `mode: enrich`. There is one writer per column,
   and `tests/check_sources.py` prints the ownership matrix.
4. Same rows, same columns: stop. This is an identity problem and needs its own
   conversation in `experimental/`.

The cross-source check rejects conflicting keys and undeclared overlapping writers
before a workspace run:

```bash
uv sync --extra dev
make test PYTHON=.venv/bin/python
.venv/bin/ruff check .
```

## What this deliberately does not do

OUT OF SCOPE for the core, permanently: deciding whether records in two
systems describe the same physical asset (matching, crosswalks, survivorship,
steward queues). That is a master-data problem, not a CFIHOS one. That layer
lives untouched in experimental/ until a customer asks the question it
answers.

See [`experimental/README.md`](experimental/README.md) for the shelved, separate
identity layer. The core does not write changes back to source systems.

## Generated model and reference data

You never need to run the parser — model.yml and src/ddl are committed artifacts.

Maintainers can reproduce them using
[`docs/model-generation.md`](docs/model-generation.md). The generated model is the
source of truth; do not hand-edit generated SQL. Reference-data loads reconcile every
input record through `cfihos_ref.load_audit` and `cfihos_ref.load_exceptions`.

The generated tables retain implementation metadata such as `spine_id`. In Core v1 it
is assigned only when a row with a new standard key is inserted; conformance matches on
the YAML `key`, not by comparing identities across source systems.

## Repository map

```text
notebooks/00_get_started.py       deploy the empty tables and load vocabulary
notebooks/01_conform.py           validate one source YAML and conform its table
tutorial/                         the three neutral demo CSVs
src/conform/sources/              source-to-standard YAML mappings
spec/                             pinned CFIHOS dictionary and Core RDL inputs
model/model.yml                   generated standard model
src/ddl/                          generated Unity Catalog table DDL
src/conform.py                    validation, row checks, MERGE, and quarantine
src/load_rdl.py                   versioned Core RDL loader
tests/check_sources.py            cross-source order and ownership checks
experimental/                     separate, shelved multi-system identity work
```

## Platform dependency ledger

The core uses only generally available (GA) platform features. Recheck availability
for the target cloud and region before deployment.

| Capability | Status | Use in this kit |
|---|---|---|
| Unity Catalog and Delta Lake | GA | Governed tables, schemas, comments, MERGE, and quarantine |
| Databricks Asset Bundles + CLI | GA | Deployment and job definitions |
| Serverless jobs | GA | Foundation, reference-data, conform, and acceptance tasks |
| Informational PK/FK constraints | GA | Model semantics and lineage; row checks enforce validity |

## Attribution and license

CFIHOS v2.0 materials are © IOGP JIP36 and are available from
<https://www.jip36-cfihos.org/cfihos-standards/>. The redistributed data-model
materials carry the Creative Commons Attribution 4.0 International (CC BY 4.0)
license. See
[`NOTICE`](NOTICE) and [`spec/VERSIONS.md`](spec/VERSIONS.md) for the exact scope,
hashes, and acquisition date. The implementation code is licensed under MIT.
