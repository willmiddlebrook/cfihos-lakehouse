# Repository operating contract (CLAUDE.md)

## Scope

This repo compiles and enforces the CFIHOS v2.0 standard
(https://www.jip36-cfihos.org/cfihos-standards/). From the standard's own
pinned files (spec/C-DM-002 dictionary XLSX + 21 Core RDL CSVs) it produces,
in a Unity Catalog catalog: the standard's tables with the standard's
definitions as column comments; required fields enforced with real NOT NULL;
the vocabulary loaded as queryable lookup tables in cfihos_ref; and a conform
step that lands valid rows in the model and quarantines invalid rows with
plain-English reasons. The standard, compiled and enforced — nothing else.

OUT OF SCOPE for the core, permanently: deciding whether records in two
systems describe the same physical asset (matching, crosswalks, survivorship,
steward queues). That is a master-data problem, not a CFIHOS one. That layer
lives untouched in experimental/ until a customer asks the question it
answers.

## Module disposition (the map of this exact tree)

KEEP — already correct, do not redesign:
- src/parse_dictionary.py — XLSX -> model/model.yml; stdlib parser; zero
  exceptions on the pinned dictionary (139 entities / 664 attributes).
- src/gen_ddl.py — model -> subject-area DDL. FKs are emitted ONLY to the
  generated entity set (tests/test_ddl.py enforces this); goldens in src/ddl
  are committed and CI checks they regenerate byte-identical.
- src/load_rdl.py — versioned Core RDL loader; 42,472 loaded + 1,281
  explained duplicate exceptions = 43,753, reconciled in load_audit.
- src/deploy_foundation.py — applies sorted src/ddl/*.sql; ensure_catalog()
  checks SHOW CATALOGS before creating (workspaces without CREATE CATALOG
  privilege pre-create and it proceeds).
- The _SCRIPT_PATH pattern in every entrypoint
  (Path(globals().get("__file__", sys.argv[0]))): serverless python tasks
  may lack __file__; a contract test enforces this pattern — keep it in any
  new entrypoint.
- spec/ (hash-pinned inputs, VERSIONS.md), model/, NOTICE, CI drift check,
  tests: test_dictionary, test_rdl, test_ddl, and the ensure_catalog and
  _SCRIPT_PATH contract tests.

BUILD — the core additions (see the core-v1 build prompt):
- src/conform.py — the enforcer. One-page YAML per source table:
  source / into / from / key / mode (upsert|enrich) / territory (optional) /
  fields / value_maps. Behaviors that are part of the product's API:
  trim strings and treat empty string as missing; MERGE on key (re-runs
  update, never duplicate); enrich updates only its mapped columns and
  quarantines unmatched rows ("no existing <entity> to enrich"); casts
  follow model datatypes and a failed cast is a quarantine reason; every
  invalid row lands in <catalog>.cfihos_quarantine.rows with a plain-English
  reasons ARRAY (the acceptance test asserts the exact strings).
- model/generation_report.yml — gen_ddl records every considered-but-skipped
  relationship with a reason (target_out_of_scope | composite_target_key |
  renamed_key | target_has_no_single_identifier); added to the CI
  generated-files check. Skipping silently is a defect.
- src/ddl/90_foreign_keys.sql — all FKs as final ALTER statements so table
  order can never matter again.
- tests/check_sources.py — cross-source lint: identical `key` per entity;
  one writer per column unless both sources are upsert with declared
  territory; topological run order printed; ownership matrix printed.
- notebooks/00_get_started and notebooks/01_conform — Databricks notebook
  source format; cells only set widgets, import from src/, and display.
  Notebooks are thin wrappers, never a second implementation.
- src/conform/sources/ — demo_plants.yml, demo_process_units.yml,
  demo_tags.yml matching the fixture CSVs in the README.

MOVE to experimental/ — the identity layer, shelved intact:
- src/onramp/ (engine, config_schema, example_cmms.yml), src/trust/
  (who_wins, merge_service, ddl_idmap, health_views), src/validate.py,
  src/front_door/, docs/source-interview.md, tests/test_onramp.py,
  tests/test_trust.py, tests/test_acceptance.py (old), tests/check_contracts.py,
  tests/verify.sql; remove the onramp and validate jobs from
  resources/jobs.yml (core jobs: foundation, load_rdl, conform, acceptance).
- experimental/README.md: one line of scope, plus two KNOWN OPEN ISSUES to
  record verbatim: (1) engine.py re-runs re-insert already-mapped rows into
  id_map (new_maps includes `direct`); (2) who_wins compares values
  null-unsafely in the additions join and conflicts filter. Do not fix
  shelved code; document it.

## Non-negotiable guardrails

1. GA or Public Preview platform features only; never Beta or Private
   Preview, including in DEV.
2. No customer or source-system vendor names anywhere: code, docs, comments,
   object names, fixtures.
3. Preserve IOGP JIP36 attribution and CC BY 4.0 notices. "CFIHOS
   v2.0-aligned," never "certified."
4. Nothing is silently dropped or invented: every rejected row reaches
   cfihos_quarantine.rows with a plain-English reason; every skipped
   generation decision reaches model/generation_report.yml; RDL load
   exceptions stay explained in load_audit/load_exceptions.
5. model/model.yml is the generated source of truth. Change the parser and
   regenerate; never hand-edit generated SQL.
6. Minimality: if a feature is not required to compile or enforce the
   standard, it does not enter the core. Identity questions go to
   experimental/, not into conform.

## Adding sources (the only four cases)

Every source maps to the model, never to another source. Classify each new
YAML: (1) feeds a new entity -> run after its parents (check_sources prints
the order; a missing parent quarantines with a plain reason); (2) same
entity, different rows -> identical `key`, declare `territory`; (3) same
rows, different columns -> mode: enrich, one writer per column
(check_sources prints the ownership matrix); (4) same rows, same columns ->
STOP: identity problem, experimental/ territory, its own conversation.

## Build loop and acceptance contract

After any code change: `make test` (regenerates model + DDL, then pytest,
including check_sources). Done means the CSV acceptance passes with these
exact results against a fresh throwaway catalog: 1 plant, 2 process units,
6 tags landed; 2 rows quarantined with exactly
"process_unit_code is required and missing" and
"WIDGET is not a valid tag class"; a second conform run changes nothing.

## Naming and platform conventions

Lowercase snake case everywhere. Schemas: cfihos_<subject_area>, cfihos_ref,
cfihos_quarantine. Always three-part names. Serverless jobs; no DBFS paths.
Catalog names are validated identifiers before any SQL interpolation.

## Core v1 status

The core-v1 build is complete. Core work follows the Scope and guardrails
above; the separate identity layer remains shelved under `experimental/`.
