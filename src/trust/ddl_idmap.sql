-- CFIHOS materials are published by IOGP JIP36 under CC BY 4.0.
-- This output is CFIHOS v2.0-aligned; it is not CFIHOS certified.
-- All declared constraints are informational; validation jobs perform enforcement.

CREATE SCHEMA IF NOT EXISTS ${catalog}.cfihos_trust
COMMENT 'Inspectable identity, stewardship, survivorship, and validation records';

CREATE SCHEMA IF NOT EXISTS ${catalog}.cfihos_onramp
COMMENT 'Configuration-driven source staging and exception surfaces';

CREATE SCHEMA IF NOT EXISTS ${catalog}.cfihos_front_door
COMMENT 'Shared semantic views for dashboards and natural-language exploration';

CREATE SCHEMA IF NOT EXISTS ${catalog}.cfihos_ref
COMMENT 'Versioned CFIHOS reference data; writable only by the RDL loader';

CREATE TABLE IF NOT EXISTS ${catalog}.cfihos_ref.load_exceptions (
  exception_id STRING NOT NULL,
  rdl_version STRING NOT NULL,
  file STRING NOT NULL,
  line BIGINT NOT NULL,
  reason STRING NOT NULL,
  raw_row STRING,
  explained BOOLEAN NOT NULL,
  recorded_at TIMESTAMP NOT NULL
) USING DELTA
COMMENT 'Rows rejected by the RDL loader; no parse failure is silently skipped';

CREATE TABLE IF NOT EXISTS ${catalog}.cfihos_ref.load_audit (
  rdl_version STRING NOT NULL,
  file STRING NOT NULL,
  table_name STRING NOT NULL,
  encoding STRING NOT NULL,
  source_rows BIGINT NOT NULL,
  loaded_rows BIGINT NOT NULL,
  exception_rows BIGINT NOT NULL,
  loaded_at TIMESTAMP NOT NULL
) USING DELTA
COMMENT 'Per-file reconciliation evidence for each RDL load';

CREATE TABLE IF NOT EXISTS ${catalog}.cfihos_trust.id_map (
  source_system STRING NOT NULL COMMENT 'Portable short name from the source YAML',
  entity STRING NOT NULL COMMENT 'CFIHOS-aligned entity name',
  source_id STRING NOT NULL COMMENT 'Identifier assigned by the source system',
  spine_id STRING NOT NULL COMMENT 'Golden identifier in the consolidation hub',
  match_tier STRING NOT NULL COMMENT 'exact, normalized, or steward',
  matched_at TIMESTAMP NOT NULL COMMENT 'Time the same-thing decision was recorded',
  matched_by STRING NOT NULL COMMENT 'Engine or steward that recorded the decision',
  CONSTRAINT pk_id_map PRIMARY KEY (source_system, entity, source_id) NOT ENFORCED
) USING DELTA
COMMENT 'Crosswalk from every source identifier to the golden identifier; PK is informational';

CREATE TABLE IF NOT EXISTS ${catalog}.cfihos_trust.review_queue (
  queue_id STRING NOT NULL,
  run_id STRING NOT NULL,
  source_system STRING NOT NULL,
  entity STRING NOT NULL,
  source_id STRING NOT NULL,
  candidate_spine_id STRING,
  evidence STRING NOT NULL COMMENT 'JSON evidence for and against the candidate',
  reason STRING NOT NULL,
  status STRING NOT NULL COMMENT 'open, confirmed, or rejected',
  resolved_by STRING,
  resolved_at TIMESTAMP,
  created_at TIMESTAMP NOT NULL,
  CONSTRAINT pk_review_queue PRIMARY KEY (queue_id) NOT ENFORCED
) USING DELTA
COMMENT 'Conservative stewardship queue; no below-tier match is silently accepted';

CREATE TABLE IF NOT EXISTS ${catalog}.cfihos_trust.merge_audit (
  event_id STRING NOT NULL,
  event_type STRING NOT NULL COMMENT 'merge or unmerge',
  survivor_spine_id STRING NOT NULL,
  absorbed_spine_id STRING NOT NULL,
  prior_state_json STRING NOT NULL,
  actor STRING NOT NULL,
  reason STRING NOT NULL,
  event_at TIMESTAMP NOT NULL,
  reverses_event_id STRING,
  CONSTRAINT pk_merge_audit PRIMARY KEY (event_id) NOT ENFORCED
) USING DELTA
COMMENT 'Append-only merge and unmerge events with enough prior state for reversal';

CREATE TABLE IF NOT EXISTS ${catalog}.cfihos_trust.attribute_conflicts (
  conflict_id STRING NOT NULL,
  run_id STRING NOT NULL,
  entity STRING NOT NULL,
  spine_id STRING NOT NULL,
  attribute STRING NOT NULL,
  conflict_type STRING NOT NULL COMMENT 'losing_claim or tied_rank',
  source_system STRING NOT NULL,
  value STRING,
  wins_rank INT NOT NULL,
  winning_source STRING,
  winning_value STRING,
  recorded_at TIMESTAMP NOT NULL,
  CONSTRAINT pk_attribute_conflicts PRIMARY KEY (conflict_id) NOT ENFORCED
) USING DELTA
COMMENT 'Losing and tied source claims retained rather than deleted or arbitrarily resolved';

CREATE TABLE IF NOT EXISTS ${catalog}.cfihos_trust.published_attributes (
  entity STRING NOT NULL,
  spine_id STRING NOT NULL,
  attribute STRING NOT NULL,
  value STRING,
  winning_source STRING NOT NULL,
  wins_rank INT NOT NULL,
  valid_from TIMESTAMP NOT NULL,
  valid_to TIMESTAMP,
  is_current BOOLEAN NOT NULL
) USING DELTA
COMMENT 'Generic SCD2 publication of winning canonical attribute values';

CREATE TABLE IF NOT EXISTS ${catalog}.cfihos_trust.validation_results (
  validation_run_id STRING NOT NULL,
  check_name STRING NOT NULL,
  object_name STRING NOT NULL,
  failed_rows BIGINT NOT NULL,
  status STRING NOT NULL,
  details STRING,
  checked_at TIMESTAMP NOT NULL
) USING DELTA
COMMENT 'Executable enforcement results for informational model constraints';

CREATE TABLE IF NOT EXISTS ${catalog}.cfihos_onramp.source_config (
  source STRING NOT NULL,
  config_yaml STRING NOT NULL,
  config_hash STRING NOT NULL,
  deployed_at TIMESTAMP NOT NULL,
  CONSTRAINT pk_source_config PRIMARY KEY (source) NOT ENFORCED
) USING DELTA
COMMENT 'Queryable Delta twin of every checked-in source configuration';

CREATE TABLE IF NOT EXISTS ${catalog}.cfihos_onramp.unmapped_codes (
  exception_id STRING NOT NULL,
  run_id STRING NOT NULL,
  source STRING NOT NULL,
  source_id STRING NOT NULL,
  entity STRING NOT NULL,
  attribute STRING NOT NULL,
  source_value STRING NOT NULL,
  recorded_at TIMESTAMP NOT NULL,
  CONSTRAINT pk_unmapped_codes PRIMARY KEY (exception_id) NOT ENFORCED
) USING DELTA
COMMENT 'Source codes blocked from publication because no explicit RDL translation exists';

CREATE TABLE IF NOT EXISTS ${catalog}.cfihos_onramp.staged_claims (
  run_id STRING NOT NULL,
  source_system STRING NOT NULL,
  entity STRING NOT NULL,
  spine_id STRING NOT NULL,
  attribute STRING NOT NULL,
  value STRING,
  wins_rank INT NOT NULL,
  observed_at TIMESTAMP NOT NULL
) USING DELTA
COMMENT 'Translated matched claims awaiting ranked survivorship';
