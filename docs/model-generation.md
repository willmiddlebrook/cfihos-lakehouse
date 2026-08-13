> Origin: This maintainer procedure is original to this kit and licensed under MIT.

# Regenerating the CFIHOS-aligned model

CFIHOS means Capital Facilities Information Handover Specification. For the operator
workflow, start with the [repository guide](../README.md).

Workspace users do not need to run the parser. `model/model.yml`, the generation
report, and `src/ddl/` are committed build artifacts. This procedure is for
maintainers updating the pinned CFIHOS input or the generation rules.

## Pinned inputs

The machine-readable inputs are:

- `spec/C-DM-002-Data-Dictionary-V2.0.xlsx`, which defines entities, attributes,
  definitions, requirements, relationships, and sections.
- The 21 Core RDL v2.0 CSVs under `spec/rdl/`, which provide reference classes,
  properties, units, document types, disciplines, and their relationships.

Their versions, acquisition date, and hashes are recorded in `spec/VERSIONS.md`.
CFIHOS materials are © IOGP JIP36 and the redistributed data-model materials are
licensed under CC BY 4.0.

## Current generation evidence

The strict XLSX parser produces 139 entities and 664 attributes, preserves the
relationship cardinality text, and writes every rejected row to
`model/parse_exceptions.yml`. The pinned v2.0 dictionary currently parses with no
exceptions.

The deployment generation profile selects 15 of those 139 entity definitions and
generates tables only for that set. Definitions outside the 15 remain available in
`model/model.yml`; they are not deployed tables.

The Core RDL contains 43,753 CSV records. After normalization, 42,472 natural keys
are unique and 1,281 rows are byte-for-byte duplicates. The loader records each
duplicate as an explained exception, so all source records reconcile and none is
silently discarded.

## Regeneration loop

From the repository root:

```bash
uv sync --extra dev
make generate PYTHON=.venv/bin/python
make test PYTHON=.venv/bin/python
git diff -- model/model.yml model/parse_exceptions.yml model/generation_report.yml src/ddl
```

`src/parse_dictionary.py` turns C-DM-002 into the canonical YAML contract.
`src/gen_ddl.py` consumes that contract and writes the subject-area DDL plus its
foreign-key generation report. Never edit generated SQL directly; change the parser
or generation profile, regenerate, and review the complete diff.

When a later CFIHOS v2.x release ships, pin and hash the new official artifacts,
update the parser only for evidenced format changes, regenerate, run the full test
suite, and perform a fresh-catalog acceptance run before release.
