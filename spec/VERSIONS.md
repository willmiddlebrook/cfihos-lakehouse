# Pinned CFIHOS inputs

Acquired from <https://www.jip36-cfihos.org/cfihos-standards/> on 2026-08-13.

| Artifact | Version | SHA-256 | Repository location |
|---|---:|---|---|
| C-DM-002 Data Dictionary | 2.0 FINAL | `65262c62aec49e3a70225d8add4d9658d98a1dd5e18082c6155e94f3ec0db5a1` | `spec/C-DM-002-Data-Dictionary-V2.0.xlsx` |
| CORE-CFIHOS-CSV archive | 2.0 | `a69b98012d9e4a46495a3aed48eef8ce75a69d001eaa28b4c38cb0f3c921909d` | unpacked into `spec/rdl/` |
| Sorted unpacked CSV hash manifest | 2.0 | `2cc15961511f5912fa11a078fb3b0748fe9796fe371701eecf996ddd7b114f8d` | 21 files in `spec/rdl/` |

The dictionary XLSX is the machine-readable model source. The Core RDL CSVs are
the deployable reference seed. The presentation data model is intentionally not
parsed. Specification and implementation-guide documents provide human context but
are not build inputs and are therefore not duplicated in this source repository.

CFIHOS materials are published free of charge by IOGP JIP36. The data-model
documents carry the CC BY 4.0 license. Preserve attribution when redistributing.
