-- Latest state of every tracked video, with time-window flags, timing, growth and benchmarks
-- (Q3, Q8-Q12, Q15 and the assessment's "last 24h / 7d / 28d" requirements).
-- Windows are measured back from the latest capture, so the dashboard always matches the data.
CREATE OR REPLACE VIEW `{{dataset_ref}}.v_videos_latest` AS
WITH latest AS (
  SELECT capture_date, capture_ts FROM `{{dataset_ref}}.v_runs` WHERE is_latest
),
cur AS (
  SELECT d.*
  FROM `{{dataset_ref}}.v_report_daily` AS d
  JOIN latest AS l ON d.data_capture_date = l.capture_date
),
snap AS (
  SELECT video_id, data_capture_date, view_count FROM `{{dataset_ref}}.v_report_daily`
),
base7 AS (
  SELECT s.video_id, ARRAY_AGG(s.view_count ORDER BY s.data_capture_date DESC LIMIT 1)[OFFSET(0)] AS views_7d_ago
  FROM snap AS s CROSS JOIN latest AS l
  WHERE s.data_capture_date <= DATE_SUB(l.capture_date, INTERVAL 7 DAY) AND s.view_count IS NOT NULL
  GROUP BY s.video_id
),
base14 AS (
  SELECT s.video_id, ARRAY_AGG(s.view_count ORDER BY s.data_capture_date DESC LIMIT 1)[OFFSET(0)] AS views_14d_ago
  FROM snap AS s CROSS JOIN latest AS l
  WHERE s.data_capture_date <= DATE_SUB(l.capture_date, INTERVAL 14 DAY) AND s.view_count IS NOT NULL
  GROUP BY s.video_id
),
first_snap AS (
  SELECT video_id, MIN(data_capture_date) AS first_capture_date,
         ARRAY_AGG(view_count ORDER BY data_capture_date LIMIT 1)[OFFSET(0)] AS first_views
  FROM snap
  WHERE view_count IS NOT NULL
  GROUP BY video_id
),
enriched AS (
  SELECT
    c.*,
    l.capture_ts AS latest_capture_ts,
    TIMESTAMP_DIFF(l.capture_ts, c.publish_datetime_utc, HOUR) AS age_hours,
    c.publish_datetime_utc > TIMESTAMP_SUB(l.capture_ts, INTERVAL 24 HOUR) AS in_last_24h,
    c.publish_datetime_utc > TIMESTAMP_SUB(l.capture_ts, INTERVAL 7 DAY) AS in_last_7d,
    c.publish_datetime_utc > TIMESTAMP_SUB(l.capture_ts, INTERVAL 28 DAY) AS in_last_28d,
    DATE(c.publish_datetime_local) AS publish_date_local,
    EXTRACT(HOUR FROM c.publish_datetime_local) AS publish_hour_local,
    FORMAT_DATETIME('%A', c.publish_datetime_local) AS publish_weekday,
    EXTRACT(DAYOFWEEK FROM c.publish_datetime_local) AS publish_weekday_num,
    CASE
      WHEN EXTRACT(HOUR FROM c.publish_datetime_local) < 6 THEN 'Late night (00-06)'
      WHEN EXTRACT(HOUR FROM c.publish_datetime_local) < 10 THEN 'Morning (06-10)'
      WHEN EXTRACT(HOUR FROM c.publish_datetime_local) < 14 THEN 'Midday (10-14)'
      WHEN EXTRACT(HOUR FROM c.publish_datetime_local) < 18 THEN 'Afternoon (14-18)'
      WHEN EXTRACT(HOUR FROM c.publish_datetime_local) < 22 THEN 'Prime time (18-22)'
      ELSE 'Late evening (22-24)'
    END AS time_slot,
    CASE
      WHEN EXTRACT(HOUR FROM c.publish_datetime_local) < 6 THEN 1
      WHEN EXTRACT(HOUR FROM c.publish_datetime_local) < 10 THEN 2
      WHEN EXTRACT(HOUR FROM c.publish_datetime_local) < 14 THEN 3
      WHEN EXTRACT(HOUR FROM c.publish_datetime_local) < 18 THEN 4
      WHEN EXTRACT(HOUR FROM c.publish_datetime_local) < 22 THEN 5
      ELSE 6
    END AS time_slot_order,
    IFNULL(c.like_count, 0) + IFNULL(c.comment_count, 0) AS engagement,
    SAFE_DIVIDE(IFNULL(c.like_count, 0) + IFNULL(c.comment_count, 0), c.view_count) AS engagement_rate,
    SAFE_DIVIDE(c.view_count, GREATEST(TIMESTAMP_DIFF(l.capture_ts, c.publish_datetime_utc, HOUR), 24) / 24.0) AS views_per_day,
    CASE
      WHEN TIMESTAMP_DIFF(l.capture_ts, c.publish_datetime_utc, HOUR) < 24 THEN '1) 0-1 day'
      WHEN TIMESTAMP_DIFF(l.capture_ts, c.publish_datetime_utc, HOUR) < 72 THEN '2) 1-3 days'
      WHEN TIMESTAMP_DIFF(l.capture_ts, c.publish_datetime_utc, HOUR) < 168 THEN '3) 3-7 days'
      WHEN TIMESTAMP_DIFF(l.capture_ts, c.publish_datetime_utc, HOUR) < 336 THEN '4) 7-14 days'
      WHEN TIMESTAMP_DIFF(l.capture_ts, c.publish_datetime_utc, HOUR) < 672 THEN '5) 14-28 days'
      ELSE '6) 28+ days'
    END AS age_bucket,
    -- growth over the last 7 days of captures
    CASE
      WHEN b7.views_7d_ago IS NOT NULL THEN c.view_count - b7.views_7d_ago
      WHEN c.publish_datetime_utc > TIMESTAMP_SUB(l.capture_ts, INTERVAL 7 DAY) THEN c.view_count
      ELSE c.view_count - f.first_views
    END AS views_gained_7d,
    CASE
      WHEN b7.views_7d_ago IS NOT NULL OR c.publish_datetime_utc > TIMESTAMP_SUB(l.capture_ts, INTERVAL 7 DAY)
        THEN 'Full 7 days'
      ELSE CONCAT('Partial (since ', CAST(f.first_capture_date AS STRING), ')')
    END AS growth_basis,
    CASE
      WHEN b7.views_7d_ago IS NOT NULL AND b14.views_14d_ago IS NOT NULL THEN b7.views_7d_ago - b14.views_14d_ago
      WHEN b7.views_7d_ago IS NOT NULL AND c.publish_datetime_utc > TIMESTAMP_SUB(l.capture_ts, INTERVAL 14 DAY)
        THEN b7.views_7d_ago
    END AS views_gained_prev_7d
  FROM cur AS c
  CROSS JOIN latest AS l
  LEFT JOIN base7 AS b7 ON b7.video_id = c.video_id
  LEFT JOIN base14 AS b14 ON b14.video_id = c.video_id
  LEFT JOIN first_snap AS f ON f.video_id = c.video_id
),
peers AS (
  -- benchmarks = medians of videos with the same format and the same age
  SELECT
    video_format,
    age_bucket,
    COUNT(*) AS peer_count,
    APPROX_QUANTILES(view_count, 100)[OFFSET(50)] AS peer_median_views,
    APPROX_QUANTILES(SAFE_DIVIDE(views_gained_7d, views_gained_prev_7d), 100)[OFFSET(50)] AS peer_median_wow_ratio,
    COUNTIF(views_gained_prev_7d > 0) AS peer_wow_count
  FROM enriched
  WHERE view_count IS NOT NULL
  GROUP BY video_format, age_bucket
)
SELECT
  e.*,
  p.peer_count,
  p.peer_median_views,
  SAFE_DIVIDE(e.view_count, p.peer_median_views) AS performance_index,
  CASE
    WHEN p.peer_count IS NULL OR p.peer_count < 5 OR p.peer_median_views = 0 THEN 'No benchmark'
    WHEN SAFE_DIVIDE(e.view_count, p.peer_median_views) >= 2 THEN '1) Top performer (2x+ median)'
    WHEN SAFE_DIVIDE(e.view_count, p.peer_median_views) >= 1 THEN '2) Above median'
    WHEN SAFE_DIVIDE(e.view_count, p.peer_median_views) >= 0.5 THEN '3) Below median'
    ELSE '4) Underperformer (<0.5x median)'
  END AS performance_label,
  SAFE_DIVIDE(e.views_gained_7d - e.views_gained_prev_7d, e.views_gained_prev_7d) AS growth_wow_pct,
  p.peer_median_wow_ratio,
  -- Views naturally fall after launch, so "dropped" means falling much faster than similar videos
  CASE
    WHEN e.views_gained_prev_7d IS NULL THEN 'Not enough history'
    WHEN e.views_gained_prev_7d < 100 THEN 'Low volume'
    WHEN p.peer_wow_count < 5 OR p.peer_median_wow_ratio IS NULL OR p.peer_median_wow_ratio <= 0 THEN 'No benchmark'
    WHEN SAFE_DIVIDE(e.views_gained_7d, e.views_gained_prev_7d) < 0.5 * p.peer_median_wow_ratio
      THEN 'Dropped (fell 2x faster than peers)'
    WHEN SAFE_DIVIDE(e.views_gained_7d, e.views_gained_prev_7d) > 1.5 * p.peer_median_wow_ratio
      THEN 'Rising (holding up 1.5x better than peers)'
    ELSE 'Typical'
  END AS momentum,
  RANK() OVER (ORDER BY e.view_count DESC) AS rank_by_views,
  RANK() OVER (ORDER BY e.views_gained_7d DESC) AS rank_by_growth_7d
FROM enriched AS e
LEFT JOIN peers AS p ON p.video_format = e.video_format AND p.age_bucket = e.age_bucket;
