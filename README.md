# CFIHOS Lakehouse Kit

> This is a consolidation-style hub for analytics and AI on the CFIHOS canonical
> model. Source systems of record keep authoring their data. There is no
> write-back in scope. The kit publishes a harmonized, CFIHOS-aligned read model
> and keeps every source value and every disagreement visible.

One Databricks Asset Bundle deploys the CFIHOS v2.0-aligned foundation. One YAML
file onboards each source system. The operating targets are:

- Empty workspace to loaded Core RDL, empty spine, and configured Genie space in under one hour.
- First real extract to its first source-health report in under one day.

## Guardrails

1. Only GA and Public Preview platform features are allowed. Every Public Preview
   dependency must be marked `[PuPr]` where used and recorded in the dependency
   ledger below. Beta and Private Preview features are excluded, including from DEV.
2. Customer and source-system vendor names are prohibited in code, docs, comments,
   table names, and fixtures. The checked-in example is deliberately neutral.
3. CFIHOS materials are published free of charge by IOGP JIP36. The data-model
   documents are licensed under CC BY 4.0. Generated output is described only as
   “CFIHOS v2.0-aligned,” never as certified.
4. Nothing fails silently. Parse failures, unmapped values, below-tier matches,
   ties, losing claims, and unexplained load exceptions have named surfaces.
5. `model/model.yml` is the generated source of truth for DDL, validation, and
   producer/consumer contracts. Do not hand-edit generated DDL.
6. Unity Catalog PK/FK declarations are informational. `src/validate.py` performs
   actual enforcement; comments never imply otherwise.

## What is included

- The supplied official v2.0 dictionary and all 21 Core RDL CSVs (43,753 source rows).
- A strict XLSX parser that produces 139 entities, 664 attributes, relationships,
  cardinality text, and an explicit exception file.
- Generated v0.1 DDL for plant, process unit, tag, equipment, document, class,
  relationship, and property-value spine entities across five subject areas.
- A versioned, idempotent RDL loader with encoding normalization, row fingerprints,
  per-file reconciliation, and exception capture.
- A source-neutral stage/translate/match/publish/report engine driven by YAML.
- Inspectable ID mapping, review, merge/unmerge audit, survivorship conflicts,
  SCD2 published attributes, validation results, health views, and a UC metric view.
- A GA Genie setup sheet, a serverless bundle, local tests, deployed verification,
and a fresh-catalog acceptance job.

The source RDL contains 1,281 byte-for-byte duplicate normalized rows. The loader
publishes 42,472 unique natural keys and records those duplicates as explained load
exceptions, so all 43,753 source rows reconcile and none disappears silently.

## Quickstart

Requirements: Python 3.10+, `make`, Databricks CLI 0.218+, and access to a
Unity Catalog-enabled workspace with serverless jobs.

```bash
uv sync --extra dev
make test
databricks auth login --profile <profile>
make bundle-validate TARGET=dev CATALOG=cfihos_dev DBX_PROFILE=<profile>
make verify TARGET=dev CATALOG=cfihos_dev DBX_PROFILE=<profile>
```

`make verify` deploys the bundle, runs the foundation and Core RDL load, then runs
the real constraint validator. Configure the GA Genie space from
`src/front_door/genie_setup.md`; no Beta import/export API is used.

For the destructive-by-design fresh-catalog acceptance run, choose a dedicated
throwaway catalog name:

```bash
CFIHOS_ACCEPTANCE_CATALOG=cfihos_acceptance_001 make acceptance TARGET=dev DBX_PROFILE=<profile>
```

The caller is responsible for removing that throwaway catalog after reviewing the
acceptance evidence.

## Add a source

1. Complete `docs/source-interview.md` with the source owner.
2. Copy `src/onramp/sources/example_cmms.yml` to a neutral short name.
3. Map source fields to attributes that exist in `model/model.yml`, add explicit
   source-code translations, and assign positive `wins_rank` values.
4. Run `make test`; every YAML is contract-checked.
5. Run the bundle job with `source_config` set to the new checked-in path.

The only permitted automatic same-thing tiers are exact and uniquely normalized.
Everything else enters `cfihos_trust.review_queue`. Steward confirmation writes
`match_tier='steward'` to the ID map.

## Repository map

```text
databricks.yml                 serverless Asset Bundle
spec/                          pinned v2.0 dictionary and Core RDL
model/model.yml                generated canonical contract
src/parse_dictionary.py        XLSX to model generator
src/gen_ddl.py                 model to subject-area DDL generator
src/load_rdl.py                versioned Core RDL loader
src/onramp/                    config contract, generic engine, example
src/trust/                     ID, review, survivorship, merge, health assets
src/front_door/                metric view and Genie setup
resources/jobs.yml             foundation, load, on-ramp, validation, acceptance
tests/                         static, defect, contract, and acceptance tests
```

## Attribution and license

CFIHOS v2.0 materials are © IOGP JIP36 and are available from
<https://www.jip36-cfihos.org/cfihos-standards/>. The CFIHOS data-model documents
carry the Creative Commons Attribution 4.0 International license. See
`spec/VERSIONS.md` for exact hashes and acquisition dates. The implementation code
is licensed under the MIT License. This project is CFIHOS v2.0-aligned and is not
part of the formal CFIHOS conformance program.

## Platform dependency ledger

Verified 2026-08-13 against first-party feature documentation. Re-verify for the
target cloud and region before a customer-facing claim.

| Capability | Status | Use |
|---|---|---|
| Unity Catalog, Delta, catalogs, schemas, comments | GA | Core path |
| Databricks Asset Bundles and CLI | GA | Core path |
| Serverless jobs | GA | All bundle tasks |
| Informational PK/FK constraints | GA | Lineage and semantics; validation enforces |
| AI/BI Genie | GA | Manually configured front door |
| UC metric views | GA | Completeness KPI; no materialization |
| UNIQUE informational constraint | Public Preview | Not used |
| UC Volumes and Auto Loader | GA | Optional handover extension only |
| Delta Sharing and Marketplace | GA | Optional distribution only |

There are no Public Preview dependencies in v0.1, so no `[PuPr]` use-site tags are
present. Metric-view materialization and Genie import/export automation are excluded.
