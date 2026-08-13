# CFIHOS Lakehouse Kit

Deploy it once and you get an empty, well-labeled filing cabinet: one table per CFIHOS
(Capital Facilities Information Handover Specification) concept (tag, equipment,
document, ...), plus the standard's official vocabulary lists loaded as lookup tables
(the reference data).

## Using it is a four-step loop

1. Get your data into a table (Delta table, the governed table format, in Unity
   Catalog, the workspace catalog of governed data objects — any path).
2. Write the YAML mapping for that source.
3. Run the job.
4. Read the scoreboard (the health views) and work the "not sure" pile.

That's the whole product. Everything else in this repo is plumbing in service of those
four steps.

Read [HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md) first.

Current v0.1 scope is narrower than the filing-cabinet metaphor: the parser captures
139 entity definitions from the pinned dictionary, while the deployment profile
generates tables for 15 selected registry entities.

The result is a CFIHOS v2.0-aligned asset-information registry and conformance
workbench. One governed founding source creates the initial registry, later sources
map to it without hiding disagreements, and stewardship, validation, and source-health
evidence stay queryable.

Source systems remain systems of record and continue authoring their data; write-back
is not in scope. The kit publishes a harmonized read model for analytics and AI while
preserving source values, exceptions, and same-thing decisions.

## Quickstart in a Databricks workspace

Clone this repository as a Databricks Git folder, open
`notebooks/00_get_started.py`, and choose a throwaway Unity Catalog catalog such as
`cfihos_tutorial_<name>`. Then follow notebooks 00 through 04 in order:

1. Run notebook 00 to create the empty filing cabinet, load the official Core RDL,
   and create its upload Volume.
2. Upload both neutral files from [`tutorial/`](tutorial/README.md) to that Volume with
   Catalog Explorer.
3. Run notebook 01 with its defaults to create `bronze.example_locations`; then repeat
   it with `feed_table_name=example_assets` and `file_name=example_assets.csv`. Keep
   `source_name=example_cmms` for both feeds.
4. Run notebook 02 to preflight both configured tables, inspect the no-write report,
   and optionally run the founding source live. The `UNKNOWN` tutorial status is
   deliberately blocked as an untranslated code.
5. Run notebook 03 to read every scoreboard view and execute the validator against the
   state you just created. The tutorial does not populate the generated tag-class and
   equipment-class registry tables, so their foreign-key checks honestly report those
   two classification gaps; the official vocabulary is still queryable in
   `cfihos_ref`.
6. Use notebook 04 for any records in the human “not sure” pile.

Nothing pushes to Git unless you explicitly push. Drop the tutorial catalog when you
finish. Before editing a real mapping, [choose evaluation or implementation
mode](docs/EVALUATING.md); implementation mode uses a fork and pull requests because
the pull request is the mapping approval event.

Requirements are a Unity Catalog-enabled workspace, permission to use or create the
chosen catalog, and serverless jobs. If catalog creation is restricted, ask an
administrator to pre-create the catalog and rerun notebook 00.

## How the registry works

```text
C-DM-002 dictionary -> model/model.yml -> generated subject-area tables
Core RDL CSVs -------------------------------------> cfihos_ref
source table -> profile -> committed mapping -> dry run -> on-ramp
                                                     |-> id map / review queue
                                                     |-> ranked source claims
                                                     `-> SCD2 registry / pending records
registry + exception surfaces -> health views, metrics, validation, Genie
```

One committed source may declare itself `founding`; unmatched founding rows mint
deterministic, auditable spine identifiers. Other sources match only at the exact or
uniquely normalized tiers. Everything ambiguous remains in
`cfihos_trust.review_queue` until a steward confirms, originates, or rejects it.

Records that are missing a required value (`reason='missing'`) or carry a value that
cannot be cast to the datatype declared in `model/model.yml`
(`reason='invalid_value'`) are not partially published. They remain visible in
`cfihos_trust.pending_records` and `pending_health` until corrected. Complete records
are materialized into the generated entity tables with SCD2 history, meaning each
change closes the prior version instead of erasing it.

## Add a source

1. Complete [the five-question interview](docs/source-interview.md) with the source
   owner.
2. Use notebook 01 to turn the source extract into a governed table and create a
   deterministic profile.
3. Use notebook 02 to map fields, codes, match keys, and claim precedence, then review
   its no-write dry-run report.
4. Follow [the mapping-proposal workflow](docs/mapping-proposals.md): commit the
   profile, candidate source YAML, and proposal on a branch, then approve outcomes in
   a pull request.
5. Run the on-ramp only from the approved, committed source YAML.

Profiles can contain raw sample values and must be handled as data. When a profile is
sensitive, keep it out of Git and pin the proposal against the controlled local copy.
The mapping agent must abstain rather than guess; unmapped codes, blocked rows, and
queued records are useful conformance findings.

## Engineers and CI

Workspace evaluators can stay in the notebooks. Repository engineers and CI use these
targets:

```bash
uv sync --extra dev
make test PYTHON=.venv/bin/python
.venv/bin/ruff check .
databricks auth login --profile <profile>
make bundle-validate TARGET=dev CATALOG=cfihos_dev DBX_PROFILE=<profile>
make verify TARGET=dev CATALOG=cfihos_dev DBX_PROFILE=<profile>
```

`make verify` deploys the bundle, runs the foundation and Core RDL load, then runs the
executable validator. Before a release, use a dedicated throwaway catalog for the
destructive-by-design acceptance run:

```bash
CFIHOS_ACCEPTANCE_CATALOG=cfihos_acceptance_001 \
make acceptance TARGET=dev DBX_PROFILE=<profile>
```

Review `validation_results`, exception surfaces, and `merge_audit`; the caller removes
the acceptance catalog afterward.

## Prove it works

The [manual test walkthrough](docs/manual-test.md) will provide the step-by-step
workspace proof. Its supplied source, `MANUAL-TEST-WALKTHROUGH.md`, was not present in
the Downloads folder, so that one document remains blocked rather than being invented.
Automated and deployed acceptance commands remain available above.

You never need to run the parser — `model/model.yml` and `src/ddl` are committed
artifacts; see [the model-generation guide](docs/model-generation.md) to regenerate
when CFIHOS v2.x ships.

## Guardrails

1. Only GA and Public Preview platform features are allowed. Every Public Preview
   dependency must be marked `[PuPr]` where used and recorded in the dependency
   ledger below. Beta and Private Preview features are excluded, including from DEV.
2. Customer and source-system vendor names are prohibited in code, docs, comments,
   table names, and fixtures. The checked-in example is deliberately neutral.
3. CFIHOS materials are published by IOGP JIP36 under CC BY 4.0. Generated output is
   described only as “CFIHOS v2.0-aligned,” never as certified.
4. Nothing fails silently. Parse failures, unmapped values, below-tier matches, ties,
   losing claims, pending records, and unexplained load exceptions have named surfaces.
5. `model/model.yml` is the generated source of truth for DDL, validation, and
   producer/consumer contracts. Do not hand-edit generated DDL.
6. Unity Catalog PK/FK declarations are informational. `src/validate.py` performs
   actual enforcement; comments never imply otherwise.

## Repository map

```text
notebooks/                      guided evaluation and operator front door
tutorial/                       neutral two-feed CSVs for notebooks 01–04
docs/EVALUATING.md              evaluation versus implementation Git modes
docs/mapping-proposals.md       review and approval workflow
spec/                           pinned CFIHOS v2.0 dictionary and Core RDL
model/model.yml                 generated canonical contract
src/parse_dictionary.py         XLSX-to-model generator
src/gen_ddl.py                  model-to-subject-area DDL generator
src/load_rdl.py                 versioned Core RDL loader
src/onramp/                     profiler, contracts, proposals, and generic engine
src/trust/                      identity, survivorship, materialization, stewardship
src/front_door/                 health metrics and Genie setup
resources/jobs.yml              serverless bundle jobs
tests/                          contract, defect, provenance, and acceptance tests
```

## Optional extensions

The core path intentionally excludes handover/file-arrival automation, a retention
policy for `staged_claims`, and Marketplace or Delta Sharing distribution of the
reference data. PDF fact extraction and document file-pointer registration are not
deployed in v0.1. UC Volumes are used only by the guided upload notebook; the on-ramp
contract consumes governed Delta tables.

## Industry terms

| Industry term | Plain meaning in this kit |
|---|---|
| Crosswalk | The ID map connecting each source identifier to one spine ID |
| Golden record | The current registry row assembled from the winning source claims |
| Registry / spine | The one-row-per-real-asset CFIHOS tables |
| Master data management (MDM) consolidation hub | A read model that reconciles source systems without writing changes back to them |
| Survivorship / source precedence | The ranked who-wins rules used when sources disagree |
| Slowly changing dimension type 2 (SCD2) | History that closes a prior row version and inserts the changed version |

## Attribution and license

CFIHOS v2.0 materials are © IOGP JIP36 and are available from
<https://www.jip36-cfihos.org/cfihos-standards/>. The redistributed data-model
materials carry the Creative Commons Attribution 4.0 International license. See
[`NOTICE`](NOTICE), [the provenance register](docs/PROVENANCE.md), and
`spec/VERSIONS.md` for exact scope, hashes, and acquisition dates. The implementation
code is licensed under MIT. This project is CFIHOS v2.0-aligned and is not part of the
formal CFIHOS conformance program.

## Platform dependency ledger

Verified 2026-08-13 against first-party feature documentation. Re-verify for the
target cloud and region before a user-facing claim.

| Capability | Status | Use |
|---|---|---|
| Unity Catalog, Delta, catalogs, schemas, comments | GA | Core path |
| Databricks Asset Bundles and CLI | GA | Deployment and jobs |
| Serverless jobs | GA | Bundle tasks |
| Informational PK/FK constraints | GA | Lineage and semantics; validation enforces |
| AI/BI Genie | GA | Manually configured front door |
| UC metric views | GA | Completeness KPI; no materialization |
| UC Volumes and `read_files` | GA | Guided file-to-table convenience |
| `ai_parse_document` | Public Preview | Optional document-fact extraction `[PuPr]`; not core |
| UNIQUE informational constraint | Public Preview | Not used |
| Delta Sharing and Marketplace | GA | Optional distribution only |

The core path has no Public Preview dependency. Optional `ai_parse_document` use is
marked `[PuPr]`; metric-view materialization and Genie import/export automation remain
excluded.
