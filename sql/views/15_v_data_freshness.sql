-- Pipeline health for a "last updated" tile: latest capture and the most recent run outcome.
CREATE OR REPLACE VIEW `{{dataset_ref}}.v_data_freshness` AS
WITH run_log AS (
  SELECT
    ARRAY_AGG(STRUCT(status, started_at, message, api_units_used) ORDER BY started_at DESC LIMIT 1)[SAFE_OFFSET(0)] AS last_run,
    MAX(IF(status = 'success', finished_at, NULL)) AS last_success_at
  FROM `{{dataset_ref}}.pipeline_runs`
),
counts AS (
  SELECT
    (SELECT COUNT(*) FROM `{{dataset_ref}}.videos`) AS videos_in_catalog,
    (SELECT COUNT(*) FROM `{{dataset_ref}}.v_videos_latest`) AS videos_tracked_latest
)
SELECT
  r.capture_ts AS latest_capture_ts_utc,
  DATETIME(r.capture_ts, '{{timezone}}') AS latest_capture_local,
  r.report_date AS latest_report_date,
  TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), r.capture_ts, HOUR) AS hours_since_capture,
  run_log.last_run.status AS last_run_status,
  run_log.last_run.started_at AS last_run_started_at,
  run_log.last_run.message AS last_run_message,
  run_log.last_run.api_units_used AS last_run_api_units,
  run_log.last_success_at,
  counts.videos_in_catalog,
  counts.videos_tracked_latest
FROM `{{dataset_ref}}.v_runs` AS r
CROSS JOIN run_log
CROSS JOIN counts
WHERE r.is_latest;
