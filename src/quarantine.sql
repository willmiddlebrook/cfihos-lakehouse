-- CFIHOS materials are published by IOGP JIP36 under CC BY 4.0.
-- This output is CFIHOS v2.0-aligned; it is not CFIHOS certified.

CREATE SCHEMA IF NOT EXISTS ${catalog}.`cfihos_quarantine`
COMMENT 'Source rows that did not conform; every rejection retains plain-English reasons';

CREATE TABLE IF NOT EXISTS ${catalog}.`cfihos_quarantine`.`rows` (
  `source` STRING NOT NULL COMMENT 'Validated source name from the source YAML',
  `entity` STRING NOT NULL COMMENT 'CFIHOS entity the source row attempted to feed',
  `run_id` STRING NOT NULL COMMENT 'Conform run that first recorded this exact rejection',
  `source_key` STRING NOT NULL COMMENT 'Canonical source key serialized as JSON',
  `source_occurrence` BIGINT NOT NULL COMMENT 'Stable occurrence within duplicate source keys',
  `source_row_json` STRING NOT NULL COMMENT 'The complete original source row serialized as JSON',
  `reasons` ARRAY<STRING> NOT NULL COMMENT 'Every plain-English reason the source row was rejected',
  `quarantined_at` TIMESTAMP NOT NULL COMMENT 'Time this exact rejection was first recorded'
)
USING DELTA
COMMENT 'Rows rejected by the CFIHOS conform enforcer; every source occurrence is retained once';
