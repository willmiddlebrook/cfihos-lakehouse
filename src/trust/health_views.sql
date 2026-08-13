-- CFIHOS materials are published by IOGP JIP36 under CC BY 4.0.
-- This output is CFIHOS v2.0-aligned; it is not CFIHOS certified.

CREATE OR REPLACE VIEW ${catalog}.cfihos_trust.match_health AS
WITH matched AS (
  SELECT source_system AS source, match_tier, count(*) AS records
  FROM ${catalog}.cfihos_trust.id_map
  GROUP BY source_system, match_tier
), queued AS (
  SELECT source_system AS source, count(*) AS records
  FROM ${catalog}.cfihos_trust.review_queue
  WHERE status = 'open'
  GROUP BY source_system
), totals AS (
  SELECT source, sum(records) AS records
  FROM (
    SELECT source, records FROM matched
    UNION ALL
    SELECT source, records FROM queued
  ) all_records
  GROUP BY source
)
SELECT
  matched.source,
  matched.match_tier,
  matched.records,
  totals.records AS total_records,
  matched.records / nullif(totals.records, 0) AS match_rate
FROM matched
JOIN totals USING (source);

CREATE OR REPLACE VIEW ${catalog}.cfihos_trust.review_queue_health AS
SELECT
  source_system AS source,
  entity,
  count(*) AS open_records,
  max(timestampdiff(HOUR, created_at, current_timestamp())) AS oldest_age_hours
FROM ${catalog}.cfihos_trust.review_queue
WHERE status = 'open'
GROUP BY source_system, entity;

CREATE OR REPLACE VIEW ${catalog}.cfihos_trust.unmapped_code_health AS
SELECT source, entity, attribute, source_value, count(*) AS occurrences
FROM ${catalog}.cfihos_onramp.unmapped_codes
GROUP BY source, entity, attribute, source_value;

CREATE OR REPLACE VIEW ${catalog}.cfihos_trust.conflict_health AS
SELECT entity, attribute, conflict_type, count(*) AS open_conflicts
FROM ${catalog}.cfihos_trust.attribute_conflicts
GROUP BY entity, attribute, conflict_type;

CREATE OR REPLACE VIEW ${catalog}.cfihos_trust.load_exception_health AS
SELECT
  '__rdl__' AS source,
  rdl_version,
  file,
  count(*) AS exceptions,
  count_if(NOT explained) AS unexplained_exceptions
FROM ${catalog}.cfihos_ref.load_exceptions
GROUP BY rdl_version, file;

CREATE OR REPLACE VIEW ${catalog}.cfihos_front_door.source_health AS
WITH sources AS (
  SELECT source FROM ${catalog}.cfihos_trust.match_health
  UNION
  SELECT source FROM ${catalog}.cfihos_trust.review_queue_health
  UNION
  SELECT source FROM ${catalog}.cfihos_trust.unmapped_code_health
), matched AS (
  SELECT source, sum(records) AS matched_records, max(total_records) AS total_records
  FROM ${catalog}.cfihos_trust.match_health
  GROUP BY source
), queued AS (
  SELECT source, sum(open_records) AS review_queue_depth
  FROM ${catalog}.cfihos_trust.review_queue_health
  GROUP BY source
), unmapped AS (
  SELECT source, sum(occurrences) AS unmapped_code_count
  FROM ${catalog}.cfihos_trust.unmapped_code_health
  GROUP BY source
)
SELECT
  sources.source,
  coalesce(matched.matched_records, 0) AS matched_records,
  coalesce(matched.total_records, 0) AS total_records,
  coalesce(queued.review_queue_depth, 0) AS review_queue_depth,
  coalesce(unmapped.unmapped_code_count, 0) AS unmapped_code_count
FROM sources
LEFT JOIN matched USING (source)
LEFT JOIN queued USING (source)
LEFT JOIN unmapped USING (source);
