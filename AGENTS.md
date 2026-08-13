# Mapping-agent contract

This agent procedure is original to this kit.

These instructions apply to any coding agent asked to draft a source mapping.

## Allowed inputs

Use only:

- `src/onramp/profiles/<source>.yml`;
- `model/model.yml`;
- the CSVs under `spec/rdl/`;
- `src/onramp/config_schema.yml`;
- one existing neutral example under `src/onramp/sources/` and its proposal.

Do not inspect unrelated source integrations, production data, credentials, or
customer-specific material.

## Required outputs

On a branch, create only:

- `src/onramp/sources/<source>.yml`, the candidate configuration; and
- `src/onramp/proposals/<source>.proposal.yml`, the review evidence.

Do not modify the engine, model, generated DDL, RDL files, tests, documentation, or
another source's artifacts. The proposal is not authorization to run live; the pull
request is the approval event.

## Mapping rules

- Abstain rather than guess. A confident guess on an ambiguous column is a defect even
  when it happens to be right.
- Never invent an entity or attribute name. Use exact names from `model/model.yml`.
- Never map two source columns to one canonical attribute.
- Account for every profile column exactly once as a mapped field, feed `source_id`, or
  `abstained.columns` entry.
- Use only `certain` or `probable`. A `certain` mapping needs at least two distinct
  allowed evidence kinds.
- Never translate a source code implicitly. Put every approved translation in
  `value_maps` and every withheld translation in `abstained.codes`.
- Every value-map target must either be verified against the referenced supplied Core
  RDL or acknowledged under `unverifiable_targets` with a one-sentence basis.
- Never propose `wins_rank` without a rationale tied to the completed source interview.
- Keep names and sample content source-neutral. Profiles can contain raw values; treat
  them as data and do not commit a sensitive profile.

## Completion gate

Before finishing, run:

```bash
python -m src.onramp.validate_proposal \
  src/onramp/proposals/<source>.proposal.yml \
  --candidate src/onramp/sources/<source>.yml
make test
```

Then run the source in dry-run mode and paste the complete JSON report into the pull
request description. Do not summarize away blocked rows, unmapped codes, queued rows,
or abstentions. Reviewers approve those predicted outcomes, not the agent's intent.
