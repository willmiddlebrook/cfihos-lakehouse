-- CFIHOS materials are published by IOGP JIP36 under CC BY 4.0.
-- This generated output is CFIHOS v2.0-aligned; it is not CFIHOS certified.
-- PK/FK constraints are informational. The conform step enforces incoming rows.

CREATE SCHEMA IF NOT EXISTS ${catalog}.`cfihos_physical_asset` COMMENT 'CFIHOS v2.0-aligned physical asset subject area.' ;

CREATE TABLE IF NOT EXISTS ${catalog}.`cfihos_physical_asset`.`equipment` (
  `equipment_code` STRING NOT NULL COMMENT 'A code used to identify uniquely the equipment.',
  `plant_code` STRING COMMENT 'The plant where the equipment is or will be installed',
  `tag_name` STRING COMMENT 'The full name of a tag',
  `equipment_class_name` STRING NOT NULL COMMENT 'The full name of the tag or equipment class',
  `manufacturer_company_name` STRING COMMENT 'A name used to uniquely identify the company. who manufactures the equipment',
  `model_part_name` STRING COMMENT 'A unique name to identify the model part of the manufacturer, and that the equipment is associated with',
  `equipment_manufacturer_serial_number` STRING COMMENT 'A unique identification number for the equipment as prescribed by the manufacturer',
  `equipment_actual_purchase_date` DATE COMMENT 'The date at which the equipment was actually purchased',
  `vendor_company_name` STRING COMMENT 'The name of the company supplying (''''vendor'''') the equipment',
  `equipment_actual_installation_date` DATE COMMENT 'The date at which the equipment was actually installed',
  `equipment_actual_startup_date` DATE COMMENT 'The date at which the equipment was actually started up',
  `equipment_price` DOUBLE COMMENT 'The price of the equipment for accounting, excluding freight, shipping and insurance costs',
  `iso_currency_code` STRING COMMENT 'The currency in which the price of the equipment is labelled.',
  `equipment_warranty_end_date` DATE COMMENT 'The date at which the warrant on the equipment will end',
  `purchase_order_issuer_company_name` STRING COMMENT 'The name of the company issuing the purchase order through which this equipment was acquired',
  `purchase_order_number` STRING COMMENT 'A unique code used to identify the purchase order within the company issuing the purchase order',
  `purchase_order_item_number` BIGINT COMMENT 'A code that uniquely identifies an item in a purchase order',
  `spine_id` STRING NOT NULL COMMENT '[Implementation] Golden identifier assigned by the consolidation hub.',
  `valid_from` TIMESTAMP NOT NULL COMMENT '[Implementation] Start of validity for this published version.',
  `valid_to` TIMESTAMP COMMENT '[Implementation] End of validity for this published version; null means current.',
  `is_current` BOOLEAN NOT NULL COMMENT '[Implementation] Whether this is the current published version.',
  `recorded_at` TIMESTAMP NOT NULL COMMENT '[Implementation] Time this version was recorded by the consolidation hub.',
  CONSTRAINT `pk_equipment` PRIMARY KEY (`equipment_code`) NOT ENFORCED
)
COMMENT 'A physical device designed to perform a function CFIHOS v2.0-aligned. Declared constraints are informational; the conform step enforces incoming rows.'
TBLPROPERTIES (
  'cfihos_version' = '2.0',
  'delta.enableChangeDataFeed' = 'true',
  'constraints_enforced' = 'false'
);
