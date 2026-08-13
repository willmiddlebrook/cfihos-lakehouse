-- CFIHOS materials are published by IOGP JIP36 under CC BY 4.0.
-- This generated output is CFIHOS v2.0-aligned; it is not CFIHOS certified.
-- PK/FK constraints below are informational. The validation job performs enforcement.

CREATE SCHEMA IF NOT EXISTS ${catalog}.`cfihos_property` COMMENT 'CFIHOS v2.0-aligned property subject area.' ;

CREATE TABLE IF NOT EXISTS ${catalog}.`cfihos_property`.`property` (
  `property_name` STRING NOT NULL COMMENT 'A name that uniquely identifies the property',
  `property_definition` STRING NOT NULL COMMENT 'A definition of what the property represents',
  `property_data_type` STRING NOT NULL COMMENT 'An indication what are the type of values of the property can take',
  `property_data_type_length` BIGINT COMMENT 'The maximum length that a property value may have in a pick list',
  `cfihos_unique_code` STRING NOT NULL COMMENT 'A code that uniquely identifies the property in CFIHOS',
  `property_existence_reason_description` STRING COMMENT 'The reason why the property has been added in CFIHOS',
  `unit_of_measure_dimension_code` STRING COMMENT 'A code that uniquely identifies the unit of measure dimension',
  `property_picklist_name` STRING COMMENT 'The name by which the pick list is designated',
  `spine_id` STRING NOT NULL COMMENT '[Implementation] Golden identifier assigned by the consolidation hub.',
  `valid_from` TIMESTAMP NOT NULL COMMENT '[Implementation] Start of validity for this published version.',
  `valid_to` TIMESTAMP COMMENT '[Implementation] End of validity for this published version; null means current.',
  `is_current` BOOLEAN NOT NULL COMMENT '[Implementation] Whether this is the current published version.',
  `recorded_at` TIMESTAMP NOT NULL COMMENT '[Implementation] Time this version was recorded by the consolidation hub.',
  CONSTRAINT `pk_property` PRIMARY KEY (`property_name`) NOT ENFORCED,
  CONSTRAINT `fk_property_unit_of_measure_dimension_code` FOREIGN KEY (`unit_of_measure_dimension_code`) REFERENCES ${catalog}.`cfihos_property`.`unit_of_measure_dimension` (`unit_of_measure_dimension_code`) NOT ENFORCED,
  CONSTRAINT `fk_property_property_picklist_name` FOREIGN KEY (`property_picklist_name`) REFERENCES ${catalog}.`cfihos_property`.`property_picklist` (`property_picklist_name`) NOT ENFORCED
)
COMMENT 'A type of feature that is used to distinguish and describe tags, equipment, models) or their class CFIHOS v2.0-aligned. Declared constraints are informational; validation jobs perform enforcement.'
TBLPROPERTIES (
  'cfihos_version' = '2.0',
  'delta.enableChangeDataFeed' = 'true',
  'constraints_enforced' = 'false'
);

CREATE TABLE IF NOT EXISTS ${catalog}.`cfihos_property`.`tag_or_equipment_class_property` (
  `tag_or_equipment_class_name` STRING NOT NULL COMMENT 'The full name of the non abstract tag or equipment class to which the property applies',
  `property_name` STRING NOT NULL COMMENT 'The name of the property that applies to a tag or equipment class',
  `imperial_unit_of_measure_name` STRING COMMENT 'The Imperial unit of measure recommended for this property',
  `si_unit_of_measure_name` STRING COMMENT 'The SI (metric) unit of measure recommended for this tag or equipment class property.',
  `property_is_relevant_for_tag_indicator` BOOLEAN NOT NULL COMMENT 'An indication that the property is relevant for tags associated with the class',
  `property_relevant_for_equipment_indicator` BOOLEAN NOT NULL COMMENT 'An indicator whether the property should be provided for a given equipment.',
  `property_relevant_for_model_part_indicator` BOOLEAN NOT NULL COMMENT 'An indication whether the property must be provided by the EPC (or the manufacturer) for a given model.',
  `cfihos_unique_code` STRING NOT NULL COMMENT 'A unique identifier, assigned in the CFIHOS Reference Data Library (RDL) to the tag or equipment class property.',
  `spine_id` STRING NOT NULL COMMENT '[Implementation] Golden identifier assigned by the consolidation hub.',
  `valid_from` TIMESTAMP NOT NULL COMMENT '[Implementation] Start of validity for this published version.',
  `valid_to` TIMESTAMP COMMENT '[Implementation] End of validity for this published version; null means current.',
  `is_current` BOOLEAN NOT NULL COMMENT '[Implementation] Whether this is the current published version.',
  `recorded_at` TIMESTAMP NOT NULL COMMENT '[Implementation] Time this version was recorded by the consolidation hub.',
  CONSTRAINT `pk_tag_or_equipment_class_property` PRIMARY KEY (`tag_or_equipment_class_name`, `property_name`) NOT ENFORCED,
  CONSTRAINT `fk_tag_or_equipment_class_property_tag_or_equipment_class_name` FOREIGN KEY (`tag_or_equipment_class_name`) REFERENCES ${catalog}.`cfihos_classification`.`non_abstract_tag_or_equipment_class` (`tag_or_equipment_class_name`) NOT ENFORCED,
  CONSTRAINT `fk_tag_or_equipment_class_property_property_name` FOREIGN KEY (`property_name`) REFERENCES ${catalog}.`cfihos_property`.`property` (`property_name`) NOT ENFORCED
)
COMMENT 'A characteristic, or property, that a tag or equipment class has CFIHOS v2.0-aligned. Declared constraints are informational; validation jobs perform enforcement.'
TBLPROPERTIES (
  'cfihos_version' = '2.0',
  'delta.enableChangeDataFeed' = 'true',
  'constraints_enforced' = 'false'
);

CREATE TABLE IF NOT EXISTS ${catalog}.`cfihos_property`.`tag_class_property` (
  `tag_class_name` STRING NOT NULL COMMENT 'The full name of the non abstract tag or equipment class to which the property applies',
  `property_name` STRING NOT NULL COMMENT 'The name of the property that applies to a tag or equipment class',
  `spine_id` STRING NOT NULL COMMENT '[Implementation] Golden identifier assigned by the consolidation hub.',
  `valid_from` TIMESTAMP NOT NULL COMMENT '[Implementation] Start of validity for this published version.',
  `valid_to` TIMESTAMP COMMENT '[Implementation] End of validity for this published version; null means current.',
  `is_current` BOOLEAN NOT NULL COMMENT '[Implementation] Whether this is the current published version.',
  `recorded_at` TIMESTAMP NOT NULL COMMENT '[Implementation] Time this version was recorded by the consolidation hub.',
  CONSTRAINT `pk_tag_class_property` PRIMARY KEY (`tag_class_name`, `property_name`) NOT ENFORCED
)
COMMENT 'A characteristic, or property, that a tag class has CFIHOS v2.0-aligned. Declared constraints are informational; validation jobs perform enforcement.'
TBLPROPERTIES (
  'cfihos_version' = '2.0',
  'delta.enableChangeDataFeed' = 'true',
  'constraints_enforced' = 'false'
);

CREATE TABLE IF NOT EXISTS ${catalog}.`cfihos_property`.`equipment_class_property` (
  `equipment_class_name` STRING NOT NULL COMMENT 'The full name of the non abstract tag or equipment class to which the property applies',
  `property_name` STRING NOT NULL COMMENT 'The name of the property that applies to a tag or equipment class',
  `property_relevant_for_equipment_indicator` BOOLEAN NOT NULL COMMENT 'An indicator whether the property should be provided for a given equipment',
  `property_relevant_for_model_part_indicator` BOOLEAN NOT NULL COMMENT 'An indication whether the property must be provided by the EPC (or the manufacturer) for a given model',
  `spine_id` STRING NOT NULL COMMENT '[Implementation] Golden identifier assigned by the consolidation hub.',
  `valid_from` TIMESTAMP NOT NULL COMMENT '[Implementation] Start of validity for this published version.',
  `valid_to` TIMESTAMP COMMENT '[Implementation] End of validity for this published version; null means current.',
  `is_current` BOOLEAN NOT NULL COMMENT '[Implementation] Whether this is the current published version.',
  `recorded_at` TIMESTAMP NOT NULL COMMENT '[Implementation] Time this version was recorded by the consolidation hub.',
  CONSTRAINT `pk_equipment_class_property` PRIMARY KEY (`equipment_class_name`, `property_name`) NOT ENFORCED
)
COMMENT 'A characteristic, or property, that an equipment class has CFIHOS v2.0-aligned. Declared constraints are informational; validation jobs perform enforcement.'
TBLPROPERTIES (
  'cfihos_version' = '2.0',
  'delta.enableChangeDataFeed' = 'true',
  'constraints_enforced' = 'false'
);

CREATE TABLE IF NOT EXISTS ${catalog}.`cfihos_property`.`tag_property` (
  `plant_code` STRING NOT NULL COMMENT 'The plant where the tag will be installed',
  `tag_name` STRING NOT NULL COMMENT 'The full name of a tag',
  `property_name` STRING NOT NULL COMMENT 'A name that uniquely identifies the property',
  `tag_property_value` STRING NOT NULL COMMENT 'The value of the property for that tag',
  `tag_property_margin_ratio` DOUBLE COMMENT 'The total margin that has been applied on the value of the tag property, compared to what was evaluated as the process stream property',
  `reason_for_deviating_from_standard_unit_of_measure` STRING COMMENT 'The reason why the unit of measure as prescribed by the source standard as not been used to report the tag property value',
  `process_stream_code` STRING COMMENT 'The process stream from on which the tag property value is based',
  `process_activity_code` STRING COMMENT 'A code that uniquely identifies the process / activity',
  `unit_of_measure_name` STRING COMMENT 'The unique name which designates the unit.',
  `spine_id` STRING NOT NULL COMMENT '[Implementation] Golden identifier assigned by the consolidation hub.',
  `valid_from` TIMESTAMP NOT NULL COMMENT '[Implementation] Start of validity for this published version.',
  `valid_to` TIMESTAMP COMMENT '[Implementation] End of validity for this published version; null means current.',
  `is_current` BOOLEAN NOT NULL COMMENT '[Implementation] Whether this is the current published version.',
  `recorded_at` TIMESTAMP NOT NULL COMMENT '[Implementation] Time this version was recorded by the consolidation hub.',
  CONSTRAINT `pk_tag_property` PRIMARY KEY (`plant_code`, `tag_name`) NOT ENFORCED,
  CONSTRAINT `fk_tag_property_property_name` FOREIGN KEY (`property_name`) REFERENCES ${catalog}.`cfihos_property`.`property` (`property_name`) NOT ENFORCED,
  CONSTRAINT `fk_tag_property_unit_of_measure_name` FOREIGN KEY (`unit_of_measure_name`) REFERENCES ${catalog}.`cfihos_property`.`unit_of_measure` (`unit_of_measure_name`) NOT ENFORCED
)
COMMENT 'A characteristic, or property, that a tag has CFIHOS v2.0-aligned. Declared constraints are informational; validation jobs perform enforcement.'
TBLPROPERTIES (
  'cfihos_version' = '2.0',
  'delta.enableChangeDataFeed' = 'true',
  'constraints_enforced' = 'false'
);

CREATE TABLE IF NOT EXISTS ${catalog}.`cfihos_property`.`equipment_property` (
  `equipment_code` STRING NOT NULL COMMENT 'A code used to identify uniquely the equipment',
  `property_name` STRING NOT NULL COMMENT 'A name that uniquely identifies the property',
  `equipment_property_value` STRING NOT NULL COMMENT 'The value of that property for this equipment.',
  `reason_for_deviating_from_standard_unit_of_measure` STRING COMMENT 'The reason why the unit of measure as prescribed by the source standard as not been used to report the equipment property value',
  `unit_of_measure_name` STRING COMMENT 'The unique name which designates the unit.',
  `spine_id` STRING NOT NULL COMMENT '[Implementation] Golden identifier assigned by the consolidation hub.',
  `valid_from` TIMESTAMP NOT NULL COMMENT '[Implementation] Start of validity for this published version.',
  `valid_to` TIMESTAMP COMMENT '[Implementation] End of validity for this published version; null means current.',
  `is_current` BOOLEAN NOT NULL COMMENT '[Implementation] Whether this is the current published version.',
  `recorded_at` TIMESTAMP NOT NULL COMMENT '[Implementation] Time this version was recorded by the consolidation hub.',
  CONSTRAINT `pk_equipment_property` PRIMARY KEY (`equipment_code`, `property_name`) NOT ENFORCED,
  CONSTRAINT `fk_equipment_property_equipment_code` FOREIGN KEY (`equipment_code`) REFERENCES ${catalog}.`cfihos_physical_asset`.`equipment` (`equipment_code`) NOT ENFORCED,
  CONSTRAINT `fk_equipment_property_property_name` FOREIGN KEY (`property_name`) REFERENCES ${catalog}.`cfihos_property`.`property` (`property_name`) NOT ENFORCED,
  CONSTRAINT `fk_equipment_property_unit_of_measure_name` FOREIGN KEY (`unit_of_measure_name`) REFERENCES ${catalog}.`cfihos_property`.`unit_of_measure` (`unit_of_measure_name`) NOT ENFORCED
)
COMMENT 'A characteristic, or property, that an equipment has CFIHOS v2.0-aligned. Declared constraints are informational; validation jobs perform enforcement.'
TBLPROPERTIES (
  'cfihos_version' = '2.0',
  'delta.enableChangeDataFeed' = 'true',
  'constraints_enforced' = 'false'
);
