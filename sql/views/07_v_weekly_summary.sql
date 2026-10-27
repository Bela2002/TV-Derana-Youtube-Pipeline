-- Calendar weeks (Monday start) with week-over-week change (Q5, Q6).
-- Trends use the average per day so a partial week compares fairly with a full one.
CREATE OR REPLACE VIEW `{{dataset_ref}}.v_weekly_summary` AS
WITH w AS (
  SELECT
    DATE_TRUNC(report_date, WEEK(MONDAY)) AS week_start,
    COUNT(*) AS days_with_data,
    SUM(views_gained) AS views_gained,
    SUM(subscribers_gained) AS subscribers_gained,
    SUM(uploads) AS uploads,
    SUM(likes_gained) AS likes_gained,
    SUM(comments_gained) AS comments_gained,
    SUM(engagement_gained) AS engagement_gained
  FROM `{{dataset_ref}}.v_channel_daily`
  WHERE views_gained IS NOT NULL
  GROUP BY week_start
),
w2 AS (
  SELECT
    w.*,
    SAFE_DIVIDE(views_gained, days_with_data) AS avg_daily_views,
    SAFE_DIVIDE(subscribers_gained, days_with_data) AS avg_daily_subscribers,
    LAG(views_gained) OVER (ORDER BY week_start) AS prev_week_views,
    LAG(subscribers_gained) OVER (ORDER BY week_start) AS prev_week_subscribers,
    LAG(SAFE_DIVIDE(views_gained, days_with_data)) OVER (ORDER BY week_start) AS prev_avg_daily_views,
    LAG(SAFE_DIVIDE(subscribers_gained, days_with_data)) OVER (ORDER BY week_start) AS prev_avg_daily_subscribers
  FROM w
)
SELECT
  w2.*,
  DATE_ADD(week_start, INTERVAL 6 DAY) AS week_end,
  SAFE_DIVIDE(avg_daily_views - prev_avg_daily_views, prev_avg_daily_views) AS views_wow_pct,
  SAFE_DIVIDE(avg_daily_subscribers - prev_avg_daily_subscribers, ABS(prev_avg_daily_subscribers)) AS subscribers_wow_pct,
  CASE
    WHEN prev_avg_daily_views IS NULL THEN 'No previous week'
    WHEN avg_daily_views > prev_avg_daily_views THEN 'Increasing'
    WHEN avg_daily_views < prev_avg_daily_views THEN 'Decreasing'
    ELSE 'Flat'
  END AS views_trend,
  CASE
    WHEN prev_avg_daily_subscribers IS NULL THEN 'No previous week'
    WHEN avg_daily_subscribers > prev_avg_daily_subscribers THEN 'Growing faster'
    WHEN avg_daily_subscribers < prev_avg_daily_subscribers THEN 'Growing slower'
    ELSE 'Same pace'
  END AS subscriber_trend
FROM w2;
