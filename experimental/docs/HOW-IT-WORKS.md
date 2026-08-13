This document is original to this kit.

# How this system works, in plain language

Deploy it once and you get an empty, well-labeled filing cabinet: one table per CFIHOS
(Capital Facilities Information Handover Specification) concept (tag, equipment,
document, ...), plus the standard's official vocabulary lists loaded as lookup tables
(the reference data).

> **Current v0.1 scope:** the parser captures all 139 entity definitions in the pinned
> dictionary, while the deployment profile intentionally generates tables for 15
> selected registry entities. The filing-cabinet sentence describes the conceptual
> organization; it does not mean all 139 definitions are deployed as tables today.

Then, for each of your real systems — an asset management application, an enterprise
resource planning system, a geographic information system (GIS), even a spreadsheet —
you write one small YAML mapping file (human-readable configuration) that says how
YOUR column names and YOUR codes line up with the STANDARD's. You run a job. The job
renames your columns to the standard's names, translates your codes to the standard's
codes, and sorts every incoming record into one of three buckets:

- this is an asset we already have -> it links the record to it;
- this is a new asset -> it creates it (only one special system is allowed to do this
  — see "founding source" below);
- not sure -> it goes to a pile for a human to decide.

The result is one row per real-world asset, in standard vocabulary, with a scoreboard
showing what matched, what would not translate, and where your systems disagree.

## Using it is a four-step loop

1. Get your data into a table (Delta table, the governed table format, in Unity
   Catalog, the workspace catalog of governed data objects — any path).
2. Write the YAML mapping for that source.
3. Run the job.
4. Read the scoreboard (the health views) and work the "not sure" pile.

That's the whole product. Everything else in this repo is plumbing in service of those
four steps.

## What "founding source" means

The registry starts empty, which creates a chicken-and-egg problem: the job's normal
behavior is to match incoming records against assets already in the registry — but on
day one there are none, so everything would land in the "not sure" pile forever. The
fix: you pick exactly ONE system — your most complete, most trusted one — and mark its
YAML with `origination: founding`. That marking means: this system's records are
allowed to CREATE the initial asset list, not just match against it. Every other system
can only match or go to the human pile. Think of it as the first census versus later
corrections. It is one system only, on purpose: if two systems could both create
assets, you would immediately recreate the duplicate problem this whole thing exists
to kill.

## PDFs, documents, and other unstructured sources

A PDF is two different things at once, and they take two different lanes.

Lane 1 — the FACTS inside it. A pump datasheet holds a tag number, a design pressure,
a manufacturer. The engine only eats tables, so those facts must be extracted into a
table first — an extraction step such as `ai_parse_document` [PuPr] (see the dependency
ledger for status), a third-party extraction tool, or a person typing. The extracted
table is then just another source: it gets its own small YAML, the job runs, and the
facts attach to the right assets like facts from any other system.

Lane 2 — the FILE as an artifact. The PDF is also a controlled document with a
revision. The file itself never goes through the engine: it sits in a Volume (a
governed file folder), and the document table gets one row — "datasheet XYZ, revision
2, belongs to tag P-4711, file lives at this path." The registry stores a pointer to
the file, never the file's contents.

Rule of thumb: facts flow through extraction into tables; files get registered with
pointers. A Volume is a parking lot, not a data format the engine understands —
whatever lands there becomes a table via a small loader step, and from the table onward
it is the same four-step loop.

> **Current v0.1 scope:** these PDF lanes describe the extension pattern, not a deployed
> workflow. The bundle does not extract PDF facts or generate a registry file-pointer
> column today; the generated document spine currently includes `document_master` only.
> Add the extraction step and document/file-pointer model before using this pattern.

## Glossary of this kit's terms

- registry / spine: the one-row-per-real-asset tables the whole system maintains.
- spine id: the single identifier a real asset gets, no matter how many systems know it
  under other ids.
- ID map: the table recording which source ids point to which spine id.
- founding source: the one system allowed to create the first draft of the asset list
  (above).
- claims: the attribute values a source asserts, each with a precedence rank.
- who-wins rules (survivorship): when sources disagree on a value, the ranked rules
  pick the published one; losing values are kept visible in the conflicts table.
- materializer: the step that turns winning values into actual rows in the CFIHOS
  tables (with history).
- pending records: assets that cannot get a row yet because a mandatory value is
  missing or a value cannot be cast to the model's datatype — recorded, never silently
  partial.
- review queue / steward: the "not sure" pile, and the named human who resolves it.
- health views: the scoreboard — match rates, untranslated codes, queue depth,
  conflicts, pending.
- dry run: run the job's logic with zero writes and see the report of what WOULD
  happen.

(For the wider industry vocabulary — crosswalk, golden record, master data management
(MDM) hub styles — see the [glossary in the README](../README.md#industry-terms).)
