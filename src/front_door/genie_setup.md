# Genie space setup

Use the GA Genie user interface. Do not use the Genie import/export API while that
API remains Beta; the repository guardrail excludes Beta dependencies.

1. Create a space named **CFIHOS Asset Information** and select a running SQL warehouse.
2. Add these curated objects:
   - `${catalog}.cfihos_front_door.source_health`
   - `${catalog}.cfihos_front_door.completeness_metrics`
   - `${catalog}.cfihos_trust.match_health`
   - `${catalog}.cfihos_trust.review_queue_health`
   - `${catalog}.cfihos_trust.unmapped_code_health`
   - `${catalog}.cfihos_trust.conflict_health`
   - `${catalog}.cfihos_ref.equipment_class`
   - `${catalog}.cfihos_ref.tag_class`
   - `${catalog}.cfihos_ref.document_type`
3. Add the instructions below verbatim, replacing `${catalog}` with the deployed catalog.
4. Run each example question and save a correct answer before handing the space over.

## Instructions

- This is a consolidation-style, read-only CFIHOS v2.0-aligned hub. Never imply that it
  writes back to a source system or that it is CFIHOS certified.
- A tag is a place or required function in the design. Equipment is a physical item that
  may be installed at a tag. Never use the terms interchangeably.
- Use `cfihos_front_door.source_health` for onboarding and operational-health questions.
- Use `cfihos_front_door.completeness_metrics` for completeness questions. This is the
  shared KPI definition; do not recalculate completeness from raw tables.
- Exact and normalized matches are automatic. Steward matches are explicit human
  decisions. Anything else remains in the review queue.
- Treat unmapped codes, open conflicts, review records, and unexplained load exceptions as
  visible quality issues. Never silently exclude them from a health answer.
- CFIHOS reference tables are dimensions. Join by the published CFIHOS code or class name
  stated in column comments.

## Example questions

- Which sources have the lowest match rate, and what is driving their open queue?
- Show unmapped values by canonical attribute and source.
- Which entities have tied source-precedence claims?
- What is completeness by entity?
- Which equipment classes have the most missing claimed attributes?
- Which document types are represented in the reference library?
