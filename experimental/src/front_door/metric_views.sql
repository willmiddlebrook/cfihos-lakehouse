-- CFIHOS materials are published by IOGP JIP36 under CC BY 4.0.
-- Plain UC metric views only; experimental metric-view materialization is not used.

CREATE OR REPLACE VIEW ${catalog}.cfihos_front_door.completeness_source AS
WITH claimed AS (
  SELECT entity, spine_id, count(DISTINCT attribute) AS claimed_attributes
  FROM ${catalog}.cfihos_onramp.staged_claims
  GROUP BY entity, spine_id
), populated AS (
  SELECT entity, spine_id, count(DISTINCT attribute) AS populated_attributes
  FROM ${catalog}.cfihos_trust.published_attributes
  WHERE is_current AND value IS NOT NULL
  GROUP BY entity, spine_id
)
SELECT
  claimed.entity,
  claimed.spine_id,
  claimed.claimed_attributes,
  coalesce(populated.populated_attributes, 0) AS populated_attributes
FROM claimed
LEFT JOIN populated USING (entity, spine_id);

CREATE OR REPLACE VIEW ${catalog}.cfihos_front_door.completeness_metrics
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
source: ${catalog}.cfihos_front_door.completeness_source
comment: "Shared completeness measures for dashboards and Genie"
dimensions:
  - name: Entity
    expr: entity
measures:
  - name: Claimed attributes
    expr: SUM(claimed_attributes)
  - name: Populated attributes
    expr: SUM(populated_attributes)
  - name: Completeness rate
    expr: SUM(populated_attributes) / NULLIF(SUM(claimed_attributes), 0)
$$;
