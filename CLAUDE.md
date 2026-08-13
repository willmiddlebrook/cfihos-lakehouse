# Repository operating contract

## Non-negotiable guardrails

1. Use GA or Public Preview features only. Mark every Public Preview dependency
   `[PuPr]` at its use site and in the README ledger with a verified-on date. Never
   introduce a Beta or Private Preview feature, including in DEV.
2. Never put a customer or source-system vendor name in code, docs, comments,
   object names, or sample data.
3. Preserve IOGP JIP36 attribution and CC BY 4.0 notices. Say “CFIHOS v2.0-aligned,”
   never “CFIHOS certified.”
4. Never invent or silently drop a value. Parsing errors, unmapped codes, and
   matches below exact/normalized go to their named exception tables and health views.
5. Treat `model/model.yml` as the one generated source of truth. Change the parser
   or generation profile and regenerate; do not edit generated SQL directly.
6. PK/FK declarations are informational. Enforcement belongs in `src/validate.py`,
   and generated comments must state that distinction.

## Build loop

After any code change, run `make test`. After any deployment, run `make verify`.
Do not report a task complete until the relevant target is green. Before tagging a
release, run `make acceptance` against a fresh throwaway catalog and review its
`validation_results`, exception surfaces, and merge audit.

## Naming and design

- Python, YAML keys, and SQL identifiers use lowercase snake case.
- Catalog is configurable; schemas are `cfihos_<subject_area>`.
- Source names are neutral short identifiers and belong only in source YAML.
- On-ramp behavior is generic. Extend `config_schema.yml` when a source needs a new
  capability; never add source-specific branches.
- Reference data is read-only outside `src/load_rdl.py`.
- No DBFS paths. Use workspace files for bundle code and UC Volumes for optional
  file-arrival extensions.
- Prefer serverless jobs and always use Unity Catalog three-part names.
