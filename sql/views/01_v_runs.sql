-- One row per daily capture. report_date = local calendar day the 24-hour window mostly covers
-- (date of the window midpoint in the reporting time zone).
CREATE OR REPLACE VIEW `{{dataset_ref}}.v_runs` AS
WITH runs AS (
  SELECT capture_date, MAX(capture_ts) AS capture_ts
  FROM `{{dataset_ref}}.channel_snapshots`
  GROUP BY capture_date
)
SELECT
  capture_date,
  capture_ts,
  LAG(capture_ts) OVER (ORDER BY capture_date) AS prev_capture_ts,
  DATE(TIMESTAMP_SUB(capture_ts, INTERVAL 12 HOUR), '{{timezone}}') AS report_date,
  capture_ts = MAX(capture_ts) OVER () AS is_latest
FROM runs;
