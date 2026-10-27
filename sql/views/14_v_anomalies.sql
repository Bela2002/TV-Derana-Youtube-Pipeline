-- Sudden spikes and drops (Q16).
--   Channel level: daily views outside +/- 2 standard deviations of the previous 14 days.
--   Video level  : a video gaining 3x+ its own recent daily average (and at least 1,000 views).
CREATE OR REPLACE VIEW `{{dataset_ref}}.v_anomalies` AS
WITH video_trail AS (
  SELECT
    d.*,
    AVG(d.views_gained) OVER w AS trailing_avg,
    COUNT(d.views_gained) OVER w AS trailing_points
  FROM `{{dataset_ref}}.v_video_daily` AS d
  WINDOW w AS (PARTITION BY d.video_id ORDER BY d.data_capture_date ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING)
)
SELECT
  report_date,
  'Channel' AS level,
  anomaly_flag AS anomaly,
  CAST(NULL AS STRING) AS video_id,
  CAST(NULL AS STRING) AS video_title,
  CAST(NULL AS STRING) AS category,
  views_per_day AS views,
  baseline_views_per_day AS baseline_views,
  views_z_score AS score,
  'z-score vs previous 14 days' AS score_type
FROM `{{dataset_ref}}.v_channel_daily`
WHERE anomaly_flag IN ('Spike', 'Drop')
UNION ALL
SELECT
  report_date,
  'Video' AS level,
  'Spike' AS anomaly,
  video_id,
  video_title,
  category,
  views_gained AS views,
  trailing_avg AS baseline_views,
  SAFE_DIVIDE(views_gained, trailing_avg) AS score,
  'x times own 7-day average' AS score_type
FROM video_trail
WHERE trailing_points >= 3
  AND views_gained >= 1000
  AND trailing_avg > 0
  AND views_gained >= 3 * trailing_avg;
