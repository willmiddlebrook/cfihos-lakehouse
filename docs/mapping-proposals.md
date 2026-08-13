> This procedure is original to this kit.

# Mapping proposals

Agent-authored mappings are proposals, never approvals. The on-ramp job runs only a
committed source YAML from `src/onramp/sources/`. A pull request is the approval event,
and the Git review and commit history are the audit trail.

For plain-language definitions of mapping, dry run, review queue, and founding source,
start with [How it works](HOW-IT-WORKS.md).

## Workflow

1. Run the `profile_source` bundle job for each governed table in the source. It prints
   YAML and stores the same evidence in `cfihos_onramp.source_profiles`.
2. Commit the printed profile as `src/onramp/profiles/<source>.yml`. For a source with
   multiple feed tables, combine the `tables` entries from its profile runs without
   changing their column evidence.
3. Give an agent only the inputs allowed by `AGENTS.md`. It creates a candidate
   `src/onramp/sources/<source>.yml` and
   `src/onramp/proposals/<source>.proposal.yml` on the same branch.
4. Run the proposal validator and `make test`.
5. Run the on-ramp in dry-run mode. Put the complete dry-run JSON in the pull-request
   description beside the proposal.
6. Review the predicted outcomes: mapped rows, queued rows, blocked rows, unmapped
   codes, abstentions, and winning-rank rationale. Approve outcomes, not intentions.
7. Merge only after human approval. Deploying the merged source YAML makes it eligible
   for the live on-ramp job.

Profiles contain raw sample values and must be handled as data. If a source is
sensitive, keep its profile out of Git and pin the proposal against the exact local
copy. Supply that copy at the pinned path only in the approved review environment when
running the validator; do not paste raw values into the pull request.

## Proposal contract

The proposal is YAML with this shape:

```yaml
proposal_version: 1
source: example_source
generated_by: agent/model-id
generated_at: 2026-08-13T17:00:00Z
pins:
  model_sha256: <model.metadata.source_sha256>
  rdl_version: "2.0"
  profile_file: src/onramp/profiles/example_source.yml
  profile_sha256: <sha256 of the exact profile bytes>
mappings:
  - entity: tag
    attribute: tag_name
    source_column: functional_location_code
    tier: certain
    evidence:
      - kind: name_similarity
        note: The source and canonical names describe a functional-location identifier.
      - kind: sample_fit
        note: Profile values fit the documented tag-name format.
value_map_summaries:
  - key: tag.tag_status
    distinct_seen: 6
    mapped: 5
    abstained: 1
match_on_rationale: Tag name is the interview-approved same-thing key.
wins_rank_rationale: Rank 10 reflects the source-owner-approved authority for status.
abstained:
  columns:
    - source_column: ambiguous_text
      reason: The profile and definitions do not identify one canonical attribute.
  codes:
    - key: tag.tag_status
      source_value: UNKNOWN_CODE
      reason: The source owner has not approved a canonical translation.
unverifiable_targets:
  - key: tag.tag_status
    basis: The referenced entity has no supplied Core RDL CSV, so the translation needs review.
```

Mapping tiers are limited to `certain` and `probable`. Evidence kinds are limited to
`name_similarity`, `definition_match`, `sample_fit`, and `picklist_coverage`. Every
mapping needs evidence; `certain` needs at least two distinct evidence kinds.

The validator enforces all of the following:

- proposal, candidate, and profile source names agree;
- model and profile pins are current;
- every candidate `fields` row has exactly one identical proposal mapping;
- every profile column is accounted for exactly once by a mapping, a feed `source_id`,
  or `abstained.columns`;
- value-map summaries correspond exactly to candidate `value_maps`;
- every value-map target is either present in the identifier column of its referenced
  supplied Core RDL or listed once under `unverifiable_targets` with a human-reviewable
  basis.

There is no third target state. A failed reference lookup is an error; an unverifiable
target without an acknowledgement is also an error.

Run the gate from the repository root:

```bash
python -m src.onramp.validate_proposal \
  src/onramp/proposals/<source>.proposal.yml \
  --candidate src/onramp/sources/<source>.yml
make test
```

The proposal validator does not approve the mapping. It proves that the proposal is
complete, internally consistent, pinned to its inputs, and explicit about uncertainty.
