-- One row per day for the channel (Q1-Q4, Q7, Q16).
--   views_gained        : change in lifetime channel views (all videos, any age)
--   subscribers_gained  : change in the PUBLIC subscriber count (YouTube rounds it, see docs)
--   likes/comments      : summed day-over-day changes of the tracked (recent) videos
--   uploads             : videos published inside the 24-hour capture window
--   anomaly_flag        : |z| >= 2 versus the previous 14 days (needs 7 days of history)
CREATE OR REPLACE VIEW `{{dataset_ref}}.v_channel_daily` AS
WITH ch AS (
  SELECT
    s.capture_date,
    s.capture_ts,
    s.channel_id,
    s.channel_title,
    s.subscriber_count,
    s.view_count AS lifetime_views,
    s.video_count AS lifetime_videos,
    s.subscriber_count - LAG(s.subscriber_count) OVER w AS subscribers_gained,
    s.view_count - LAG(s.view_count) OVER w AS views_gained,
    DATE_DIFF(s.capture_date, LAG(s.capture_date) OVER w, DAY) AS days_since_prev_capture
  FROM `{{dataset_ref}}.channel_snapshots` AS s
  WINDOW w AS (PARTITION BY s.channel_id ORDER BY s.capture_date)
),
vid AS (
  SELECT
    data_capture_date AS capture_date,
    SUM(views_gained) AS tracked_video_views_gained,
    SUM(likes_gained) AS likes_gained,
    SUM(comments_gained) AS comments_gained
  FROM `{{dataset_ref}}.v_video_daily`
  GROUP BY data_capture_date
),
up AS (
  SELECT
    r.capture_date,
    COUNT(*) AS uploads,
    COUNTIF(v.video_format = 'Short') AS uploads_shorts,
    COUNTIF(v.video_format = 'Long-form') AS uploads_long_form
  FROM `{{dataset_ref}}.v_runs` AS r
  CROSS JOIN `{{dataset_ref}}.videos` AS v
  WHERE r.prev_capture_ts IS NOT NULL
    AND v.published_at > r.prev_capture_ts
    AND v.published_at <= r.capture_ts
  GROUP BY r.capture_date
),
base AS (
  SELECT
    r.report_date,
    FORMAT_DATE('%A', r.report_date) AS weekday,
    EXTRACT(DAYOFWEEK FROM r.report_date) AS weekday_num,
    ch.*,
    SAFE_DIVIDE(ch.views_gained, ch.days_since_prev_capture) AS views_per_day,
    vid.tracked_video_views_gained,
    vid.likes_gained,
    vid.comments_gained,
    IFNULL(vid.likes_gained, 0) + IFNULL(vid.comments_gained, 0) AS engagement_gained,
    SAFE_DIVIDE(IFNULL(vid.likes_gained, 0) + IFNULL(vid.comments_gained, 0), vid.tracked_video_views_gained) AS engagement_rate,
    IF(r.prev_capture_ts IS NULL, NULL, IFNULL(up.uploads, 0)) AS uploads,
    IF(r.prev_capture_ts IS NULL, NULL, IFNULL(up.uploads_shorts, 0)) AS uploads_shorts,
    IF(r.prev_capture_ts IS NULL, NULL, IFNULL(up.uploads_long_form, 0)) AS uploads_long_form
  FROM ch
  LEFT JOIN `{{dataset_ref}}.v_runs` AS r ON r.capture_date = ch.capture_date
  LEFT JOIN vid ON vid.capture_date = ch.capture_date
  LEFT JOIN up ON up.capture_date = ch.capture_date
),
stats AS (
  SELECT
    base.*,
    AVG(views_per_day) OVER trail AS baseline_views_per_day,
    STDDEV_SAMP(views_per_day) OVER trail AS baseline_stddev,
    COUNT(views_per_day) OVER trail AS baseline_days,
    AVG(views_per_day) OVER (ORDER BY capture_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS views_7d_moving_avg
  FROM base
  WINDOW trail AS (ORDER BY capture_date ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING)
)
SELECT
  stats.*,
  SAFE_DIVIDE(views_per_day - baseline_views_per_day, baseline_stddev) AS views_z_score,
  CASE
    WHEN views_per_day IS NULL THEN 'No data (first capture)'
    WHEN baseline_days < 7 THEN 'Building baseline'
    WHEN SAFE_DIVIDE(views_per_day - baseline_views_per_day, baseline_stddev) >= 2 THEN 'Spike'
    WHEN SAFE_DIVIDE(views_per_day - baseline_views_per_day, baseline_stddev) <= -2 THEN 'Drop'
    ELSE 'Normal'
  END AS anomaly_flag
FROM stats;
