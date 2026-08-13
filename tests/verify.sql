-- Every query must return zero before a deployed verification is green.
SELECT count(*) AS failures
FROM ${catalog}.cfihos_ref.load_audit
WHERE source_rows <> loaded_rows + exception_rows;

SELECT count(*) AS failures
FROM ${catalog}.cfihos_ref.load_exceptions
WHERE NOT explained;

SELECT count(*) AS failures
FROM ${catalog}.cfihos_trust.validation_results
WHERE status = 'FAIL'
  AND validation_run_id = (
    SELECT max_by(validation_run_id, checked_at)
    FROM ${catalog}.cfihos_trust.validation_results
  );

SELECT count(*) AS failures
FROM ${catalog}.information_schema.tables
WHERE table_schema LIKE 'cfihos_%'
  AND comment IS NULL;
