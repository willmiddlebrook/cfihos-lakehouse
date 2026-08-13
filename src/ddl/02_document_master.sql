-- CFIHOS materials are published by IOGP JIP36 under CC BY 4.0.
-- This generated output is CFIHOS v2.0-aligned; it is not CFIHOS certified.
-- PK/FK constraints below are informational. The validation job performs enforcement.

CREATE SCHEMA IF NOT EXISTS ${catalog}.`cfihos_document_master` COMMENT 'CFIHOS v2.0-aligned document master subject area.' ;

CREATE TABLE IF NOT EXISTS ${catalog}.`cfihos_document_master`.`document_master` (
  `document_number` STRING NOT NULL COMMENT 'The unique identifier for the Document according to the Owner/Operator Document numbering scheme',
  `document_title` STRING NOT NULL COMMENT 'A description, in a short and concise manner, of the content of the document',
  `discipline_document_type_short_code` STRING NOT NULL COMMENT 'At alternate way of identifying uniquely a combination of discipline and document type',
  `document_review_type` STRING NOT NULL COMMENT 'A code that uniquely identifies a document review type',
  `forecast_review_date` DATE COMMENT 'The latest forecast date at which the document is expected to be issued for review',
  `forecast_approval_date` DATE COMMENT 'The latest forecast date at which the document is expected to be issued for approval',
  `forecast_approved_for_design_date` DATE COMMENT 'The latest forecast date at which the document is expected to be issued approved for design',
  `forecast_approved_for_construction_date` DATE COMMENT 'The latest forecast date at which the document is expected to be issued approved for construction',
  `forecast_as_built_date` DATE COMMENT 'The latest forecast date at which the document is expected to be issued as-built',
  `spine_id` STRING NOT NULL COMMENT '[Implementation] Golden identifier assigned by the consolidation hub.',
  `valid_from` TIMESTAMP NOT NULL COMMENT '[Implementation] Start of validity for this published version.',
  `valid_to` TIMESTAMP COMMENT '[Implementation] End of validity for this published version; null means current.',
  `is_current` BOOLEAN NOT NULL COMMENT '[Implementation] Whether this is the current published version.',
  `recorded_at` TIMESTAMP NOT NULL COMMENT '[Implementation] Time this version was recorded by the consolidation hub.',
  CONSTRAINT `pk_document_master` PRIMARY KEY (`document_number`) NOT ENFORCED
)
COMMENT 'A placeholder that allows a project to identify a particular information content to be created or updated CFIHOS v2.0-aligned. Declared constraints are informational; validation jobs perform enforcement.'
TBLPROPERTIES (
  'cfihos_version' = '2.0',
  'delta.enableChangeDataFeed' = 'true',
  'constraints_enforced' = 'false'
);
