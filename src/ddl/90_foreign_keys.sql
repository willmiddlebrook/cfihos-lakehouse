-- CFIHOS materials are published by IOGP JIP36 under CC BY 4.0.
-- This generated output is CFIHOS v2.0-aligned; it is not CFIHOS certified.
-- PK/FK constraints are informational. The validation job performs enforcement.

ALTER TABLE ${catalog}.`cfihos_functional_asset`.`process_unit`
ADD CONSTRAINT `fk_process_unit_plant_code` FOREIGN KEY (`plant_code`) REFERENCES ${catalog}.`cfihos_functional_asset`.`plant` (`plant_code`) NOT ENFORCED;

ALTER TABLE ${catalog}.`cfihos_functional_asset`.`tag`
ADD CONSTRAINT `fk_tag_tag_class_name` FOREIGN KEY (`tag_class_name`) REFERENCES ${catalog}.`cfihos_classification`.`tag_class` (`tag_class_name`) NOT ENFORCED;

ALTER TABLE ${catalog}.`cfihos_physical_asset`.`equipment`
ADD CONSTRAINT `fk_equipment_equipment_class_name` FOREIGN KEY (`equipment_class_name`) REFERENCES ${catalog}.`cfihos_classification`.`equipment_class` (`equipment_class_name`) NOT ENFORCED;

ALTER TABLE ${catalog}.`cfihos_classification`.`tag_class_equipment_class_relationship`
ADD CONSTRAINT `fk_tag_class_equipment_class_relationship_tag_class_name` FOREIGN KEY (`tag_class_name`) REFERENCES ${catalog}.`cfihos_classification`.`tag_class` (`tag_class_name`) NOT ENFORCED;

ALTER TABLE ${catalog}.`cfihos_classification`.`tag_class_equipment_class_relationship`
ADD CONSTRAINT `fk_tag_class_equipment_class_relationship_equipment_class_name` FOREIGN KEY (`equipment_class_name`) REFERENCES ${catalog}.`cfihos_classification`.`equipment_class` (`equipment_class_name`) NOT ENFORCED;

ALTER TABLE ${catalog}.`cfihos_property`.`tag_or_equipment_class_property`
ADD CONSTRAINT `fk_tag_or_equipment_class_property_property_name` FOREIGN KEY (`property_name`) REFERENCES ${catalog}.`cfihos_property`.`property` (`property_name`) NOT ENFORCED;

ALTER TABLE ${catalog}.`cfihos_property`.`tag_property`
ADD CONSTRAINT `fk_tag_property_property_name` FOREIGN KEY (`property_name`) REFERENCES ${catalog}.`cfihos_property`.`property` (`property_name`) NOT ENFORCED;

ALTER TABLE ${catalog}.`cfihos_property`.`equipment_property`
ADD CONSTRAINT `fk_equipment_property_equipment_code` FOREIGN KEY (`equipment_code`) REFERENCES ${catalog}.`cfihos_physical_asset`.`equipment` (`equipment_code`) NOT ENFORCED;

ALTER TABLE ${catalog}.`cfihos_property`.`equipment_property`
ADD CONSTRAINT `fk_equipment_property_property_name` FOREIGN KEY (`property_name`) REFERENCES ${catalog}.`cfihos_property`.`property` (`property_name`) NOT ENFORCED;
