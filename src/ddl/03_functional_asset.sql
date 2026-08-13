-- CFIHOS materials are published by IOGP JIP36 under CC BY 4.0.
-- This generated output is CFIHOS v2.0-aligned; it is not CFIHOS certified.
-- PK/FK constraints below are informational. The validation job performs enforcement.

CREATE SCHEMA IF NOT EXISTS ${catalog}.`cfihos_functional_asset` COMMENT 'CFIHOS v2.0-aligned functional asset subject area.' ;

CREATE TABLE IF NOT EXISTS ${catalog}.`cfihos_functional_asset`.`plant` (
  `plant_code` STRING NOT NULL COMMENT 'A code that uniquely identifies the plant',
  `plant_name` STRING NOT NULL COMMENT 'The full name of the plant',
  `site_code` STRING COMMENT 'A code that uniquely identifies the site',
  `iso_language_code` STRING COMMENT 'The language that should be used by default for all exchange of information related to that plant',
  `measurement_system_code` STRING COMMENT 'The default measurement system that is used by a plant',
  `industrial_complex_code` STRING COMMENT 'A code that uniquely identifies the industrial complex',
  `spine_id` STRING NOT NULL COMMENT '[Implementation] Golden identifier assigned by the consolidation hub.',
  `valid_from` TIMESTAMP NOT NULL COMMENT '[Implementation] Start of validity for this published version.',
  `valid_to` TIMESTAMP COMMENT '[Implementation] End of validity for this published version; null means current.',
  `is_current` BOOLEAN NOT NULL COMMENT '[Implementation] Whether this is the current published version.',
  `recorded_at` TIMESTAMP NOT NULL COMMENT '[Implementation] Time this version was recorded by the consolidation hub.',
  CONSTRAINT `pk_plant` PRIMARY KEY (`plant_code`) NOT ENFORCED,
  CONSTRAINT `fk_plant_site_code` FOREIGN KEY (`site_code`) REFERENCES ${catalog}.`cfihos_functional_asset`.`site` (`site_code`) NOT ENFORCED,
  CONSTRAINT `fk_plant_iso_language_code` FOREIGN KEY (`iso_language_code`) REFERENCES ${catalog}.`cfihos_document_master`.`iso_language` (`iso_language_code`) NOT ENFORCED,
  CONSTRAINT `fk_plant_measurement_system_code` FOREIGN KEY (`measurement_system_code`) REFERENCES ${catalog}.`cfihos_property`.`measurement_system` (`measurement_system_code`) NOT ENFORCED,
  CONSTRAINT `fk_plant_industrial_complex_code` FOREIGN KEY (`industrial_complex_code`) REFERENCES ${catalog}.`cfihos_functional_asset`.`industrial_complex` (`industrial_complex_code`) NOT ENFORCED
)
COMMENT 'An assembly of equipment that perform a physical or chemical process, including production, transportation and storage CFIHOS v2.0-aligned. Declared constraints are informational; validation jobs perform enforcement.'
TBLPROPERTIES (
  'cfihos_version' = '2.0',
  'delta.enableChangeDataFeed' = 'true',
  'constraints_enforced' = 'false'
);

CREATE TABLE IF NOT EXISTS ${catalog}.`cfihos_functional_asset`.`process_unit` (
  `plant_code` STRING NOT NULL COMMENT 'The plant the process unit is part of',
  `process_unit_code` STRING NOT NULL COMMENT 'A code that uniquely identifies the process unit within the plant',
  `process_unit_name` STRING NOT NULL COMMENT 'A name describing the function of the process unit',
  `spine_id` STRING NOT NULL COMMENT '[Implementation] Golden identifier assigned by the consolidation hub.',
  `valid_from` TIMESTAMP NOT NULL COMMENT '[Implementation] Start of validity for this published version.',
  `valid_to` TIMESTAMP COMMENT '[Implementation] End of validity for this published version; null means current.',
  `is_current` BOOLEAN NOT NULL COMMENT '[Implementation] Whether this is the current published version.',
  `recorded_at` TIMESTAMP NOT NULL COMMENT '[Implementation] Time this version was recorded by the consolidation hub.',
  CONSTRAINT `pk_process_unit` PRIMARY KEY (`plant_code`, `process_unit_code`) NOT ENFORCED,
  CONSTRAINT `fk_process_unit_plant_code` FOREIGN KEY (`plant_code`) REFERENCES ${catalog}.`cfihos_functional_asset`.`plant` (`plant_code`) NOT ENFORCED
)
COMMENT 'A decomposition of the ''''high level'''' Facility function into more granular ''''sub-functions'''' CFIHOS v2.0-aligned. Declared constraints are informational; validation jobs perform enforcement.'
TBLPROPERTIES (
  'cfihos_version' = '2.0',
  'delta.enableChangeDataFeed' = 'true',
  'constraints_enforced' = 'false'
);

CREATE TABLE IF NOT EXISTS ${catalog}.`cfihos_functional_asset`.`tag` (
  `plant_code` STRING NOT NULL COMMENT 'The plant where the tag is or will be located',
  `tag_name` STRING NOT NULL COMMENT 'The full name of a tag',
  `tag_description` STRING NOT NULL COMMENT 'A functional description of the tag',
  `parent_tag_name` STRING COMMENT 'An identification of the parentage of the tag',
  `process_unit_code` STRING NOT NULL COMMENT 'The process unit within the plant to which the tag provides part of the functionality',
  `area_code` STRING COMMENT 'The geographical area within the plant where the tag is located',
  `construction_assembly_code` STRING COMMENT 'The construction assembly of a plant where the tag resides',
  `commissioning_unit_code` STRING COMMENT 'The unit that will or has commissioned the tag',
  `maintenance_unit_code` STRING COMMENT 'The unit that is in charge of maintaining the tag',
  `maintenance_system_code` STRING COMMENT 'The maintenance system through which the tag is maintained',
  `corrosion_loop_code` STRING COMMENT 'The corrosion loop that includes the tag',
  `tag_class_name` STRING NOT NULL COMMENT 'The full name of the tag or equipment class',
  `tag_status` STRING NOT NULL COMMENT 'An identification of the engineering phase in which the tag is',
  `tag_requisition_number` STRING COMMENT 'A requisition number that has been placed to acquire the tag',
  `designed_by_company_name` STRING NOT NULL COMMENT 'The company responsible for the design of the tag.',
  `production_critical_item_indicator` BOOLEAN NOT NULL COMMENT 'An indication whether the loss of the functionality provided by the tag would have an immediate cost impact, like a loss of production',
  `safety_critical_item_indicator` BOOLEAN NOT NULL COMMENT 'An indication whether the tag should be considered as a safety critical element, as per International Standards.',
  `safety_critical_item_group_code` STRING COMMENT 'The safety critical item group assigned to the tag, and identified according to International Standard',
  `safety_critical_item_reason_awarded` STRING COMMENT 'A documentation of the outcome of the SCE assessment',
  `manufacturer_company_name` STRING COMMENT 'A name used to uniquely identify the company who manufactures the model / part',
  `model_part_name` STRING COMMENT 'A unique name to identify the model part of the manufacturer',
  `spine_id` STRING NOT NULL COMMENT '[Implementation] Golden identifier assigned by the consolidation hub.',
  `valid_from` TIMESTAMP NOT NULL COMMENT '[Implementation] Start of validity for this published version.',
  `valid_to` TIMESTAMP COMMENT '[Implementation] End of validity for this published version; null means current.',
  `is_current` BOOLEAN NOT NULL COMMENT '[Implementation] Whether this is the current published version.',
  `recorded_at` TIMESTAMP NOT NULL COMMENT '[Implementation] Time this version was recorded by the consolidation hub.',
  CONSTRAINT `pk_tag` PRIMARY KEY (`plant_code`, `tag_name`) NOT ENFORCED,
  CONSTRAINT `fk_tag_tag_class_name` FOREIGN KEY (`tag_class_name`) REFERENCES ${catalog}.`cfihos_classification`.`tag_class` (`tag_class_name`) NOT ENFORCED,
  CONSTRAINT `fk_tag_safety_critical_item_group_code` FOREIGN KEY (`safety_critical_item_group_code`) REFERENCES ${catalog}.`cfihos_physical_asset`.`safety_critical_item_group` (`safety_critical_item_group_code`) NOT ENFORCED
)
COMMENT 'An object designed for performing functional requirements and serving as a specification for equipment CFIHOS v2.0-aligned. Declared constraints are informational; validation jobs perform enforcement.'
TBLPROPERTIES (
  'cfihos_version' = '2.0',
  'delta.enableChangeDataFeed' = 'true',
  'constraints_enforced' = 'false'
);
