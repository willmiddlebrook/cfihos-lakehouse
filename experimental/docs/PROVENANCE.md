> Origin: This provenance register is original to this kit and licensed under MIT.

# Artifact provenance

This repository combines attributed CFIHOS (Capital Facilities Information Handover
Specification) v2.0 source material with an original implementation. “CFIHOS
v2.0-aligned” describes the implementation; it is not a claim of CFIHOS certification.
See [how the system works](HOW-IT-WORKS.md) for the plain-language data flow.

| Artifact class | Origin | License or treatment |
|---|---|---|
| C-DM-002 column and table comments | Verbatim definitions from the CFIHOS v2.0 data dictionary, published by IOGP JIP36 | © IOGP JIP36, CC BY 4.0; preserve attribution |
| `cfihos_ref` table structures and rows | Core CFIHOS RDL v2.0 CSV archive, published by IOGP JIP36 | © IOGP JIP36, CC BY 4.0; preserve attribution |
| Subject-area structure | C-DM-002 sections A.2–A.9 | © IOGP JIP36, CC BY 4.0; preserve attribution |
| Columns whose comments begin `[Implementation]` | Original technical metadata added by this kit | MIT |
| Parser, DDL compiler, RDL loader, and deployment orchestration | Original to this kit; they transform or deploy the attributed inputs without changing their origin | MIT implementation; emitted CFIHOS content retains CC BY 4.0 attribution |
| Source interview sheet | Original to this kit | MIT |
| On-ramp configuration contract and example | Original to this kit | MIT |
| Profiling, mapping-proposal, and dry-run procedures | Original to this kit | MIT |
| On-ramp engine and materializer | Original to this kit | MIT |
| Identity, matching, survivorship, validation, health, and stewardship machinery | Original to this kit | MIT |
| Databricks notebooks | Original to this kit | MIT |
| Neutral CSVs under `tutorial/` | Invented example records original to this kit; no operational source data | MIT |
| Asset Bundle definitions, Make targets, and tests | Original to this kit | MIT |
| Evaluation, operating, and maintainer procedures | Original to this kit | MIT |

See `spec/VERSIONS.md` for the exact source hashes and acquisition date, and
`NOTICE` for the redistribution notice.
