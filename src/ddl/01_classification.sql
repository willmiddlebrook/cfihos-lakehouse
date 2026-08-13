-- CFIHOS materials are published by IOGP JIP36 under CC BY 4.0.
-- This generated output is CFIHOS v2.0-aligned; it is not CFIHOS certified.
-- PK/FK constraints are informational. The validation job performs enforcement.

CREATE SCHEMA IF NOT EXISTS ${catalog}.`cfihos_classification` COMMENT 'CFIHOS v2.0-aligned classification subject area.' ;

CREATE TABLE IF NOT EXISTS ${catalog}.`cfihos_classification`.`tag_or_equipment_class` (
  `tag_or_equipment_class_name` STRING NOT NULL COMMENT 'The full name of the tag or equipment class',
  `parent_tag_or_equipment_class_name` STRING COMMENT 'The full name of the tag or equipment class',
  `tag_or_equipment_class_definition` STRING NOT NULL COMMENT 'A definition of what the tag or equipment class is',
  `tag_class_indicator` BOOLEAN NOT NULL COMMENT 'An indication that the tag or equipment class is considered as a tag class',
  `equipment_class_indicator` BOOLEAN NOT NULL COMMENT 'An indication that the tag or equipment class is considered as an equipment class',
  `abstract_class_indicator` BOOLEAN NOT NULL COMMENT 'An indication whether the tag or equipment class is an aggregation of other tag or equipment classes and should not be used for associating properties',
  `tag_or_equipment_class_existence_reason_description` STRING COMMENT 'An explanation of why the tag or equipment class was created / needed',
  `cfihos_unique_code` STRING NOT NULL COMMENT 'A unique identifier, assigned in the CFIHOS Reference Data Library (RDL) to the tag or equipment class',
  `spine_id` STRING NOT NULL COMMENT '[Implementation] Golden identifier assigned by the consolidation hub.',
  `valid_from` TIMESTAMP NOT NULL COMMENT '[Implementation] Start of validity for this published version.',
  `valid_to` TIMESTAMP COMMENT '[Implementation] End of validity for this published version; null means current.',
  `is_current` BOOLEAN NOT NULL COMMENT '[Implementation] Whether this is the current published version.',
  `recorded_at` TIMESTAMP NOT NULL COMMENT '[Implementation] Time this version was recorded by the consolidation hub.',
  CONSTRAINT `pk_tag_or_equipment_class` PRIMARY KEY (`tag_or_equipment_class_name`) NOT ENFORCED
)
COMMENT 'A tag class or an equipment class CFIHOS v2.0-aligned. Declared constraints are informational; validation jobs perform enforcement.'
TBLPROPERTIES (
  'cfihos_version' = '2.0',
  'delta.enableChangeDataFeed' = 'true',
  'constraints_enforced' = 'false'
);

CREATE TABLE IF NOT EXISTS ${catalog}.`cfihos_classification`.`tag_class` (
  `tag_class_name` STRING NOT NULL COMMENT 'The full name of the tag class',
  `tag_number_format` STRING COMMENT 'An expression that represents the format of the tags belonging to the tag class',
  `equipment_expected_to_be_installed_indicator` BOOLEAN NOT NULL COMMENT 'An indication whether equipment are expected to be installed for tags that are associated with this tag class',
  `spine_id` STRING NOT NULL COMMENT '[Implementation] Golden identifier assigned by the consolidation hub.',
  `valid_from` TIMESTAMP NOT NULL COMMENT '[Implementation] Start of validity for this published version.',
  `valid_to` TIMESTAMP COMMENT '[Implementation] End of validity for this published version; null means current.',
  `is_current` BOOLEAN NOT NULL COMMENT '[Implementation] Whether this is the current published version.',
  `recorded_at` TIMESTAMP NOT NULL COMMENT '[Implementation] Time this version was recorded by the consolidation hub.',
  CONSTRAINT `pk_tag_class` PRIMARY KEY (`tag_class_name`) NOT ENFORCED
)
COMMENT 'A classification of tags according to the functions they are required to perform CFIHOS v2.0-aligned. Declared constraints are informational; validation jobs perform enforcement.'
TBLPROPERTIES (
  'cfihos_version' = '2.0',
  'delta.enableChangeDataFeed' = 'true',
  'constraints_enforced' = 'false'
);

CREATE TABLE IF NOT EXISTS ${catalog}.`cfihos_classification`.`equipment_class` (
  `equipment_class_name` STRING NOT NULL COMMENT 'The full name of the equipment class',
  `spare_part_information_required_indicator` BOOLEAN NOT NULL COMMENT 'An indication whether spare part information is required for equipment related to this class or not',
  `spine_id` STRING NOT NULL COMMENT '[Implementation] Golden identifier assigned by the consolidation hub.',
  `valid_from` TIMESTAMP NOT NULL COMMENT '[Implementation] Start of validity for this published version.',
  `valid_to` TIMESTAMP COMMENT '[Implementation] End of validity for this published version; null means current.',
  `is_current` BOOLEAN NOT NULL COMMENT '[Implementation] Whether this is the current published version.',
  `recorded_at` TIMESTAMP NOT NULL COMMENT '[Implementation] Time this version was recorded by the consolidation hub.',
  CONSTRAINT `pk_equipment_class` PRIMARY KEY (`equipment_class_name`) NOT ENFORCED
)
COMMENT 'A classification of equipment and equipment models, according to its physical assembly of component(s) CFIHOS v2.0-aligned. Declared constraints are informational; validation jobs perform enforcement.'
TBLPROPERTIES (
  'cfihos_version' = '2.0',
  'delta.enableChangeDataFeed' = 'true',
  'constraints_enforced' = 'false'
);

CREATE TABLE IF NOT EXISTS ${catalog}.`cfihos_classification`.`tag_class_equipment_class_relationship` (
  `tag_class_name` STRING NOT NULL COMMENT 'The full name of the tag or equipment class',
  `equipment_class_name` STRING NOT NULL COMMENT 'The full name of the tag or equipment class',
  `tag_or_equipment_class_relationship_reason_for_mapping` STRING COMMENT 'The underlying reason why the tag class and the equipment class are related',
  `spine_id` STRING NOT NULL COMMENT '[Implementation] Golden identifier assigned by the consolidation hub.',
  `valid_from` TIMESTAMP NOT NULL COMMENT '[Implementation] Start of validity for this published version.',
  `valid_to` TIMESTAMP COMMENT '[Implementation] End of validity for this published version; null means current.',
  `is_current` BOOLEAN NOT NULL COMMENT '[Implementation] Whether this is the current published version.',
  `recorded_at` TIMESTAMP NOT NULL COMMENT '[Implementation] Time this version was recorded by the consolidation hub.',
  CONSTRAINT `pk_tag_class_equipment_class_relationship` PRIMARY KEY (`tag_class_name`, `equipment_class_name`) NOT ENFORCED
)
COMMENT 'An equipment class that can be used to implement the function of a tag class CFIHOS v2.0-aligned. Declared constraints are informational; validation jobs perform enforcement.'
TBLPROPERTIES (
  'cfihos_version' = '2.0',
  'delta.enableChangeDataFeed' = 'true',
  'constraints_enforced' = 'false'
);
