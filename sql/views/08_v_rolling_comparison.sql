-- Single row: last 7 report days vs the 7 days before (Q5, Q6 "compared to last week").
CREATE OR REPLACE VIEW `{{dataset_ref}}.v_rolling_comparison` AS
WITH latest AS (
  SELECT MAX(report_date) AS d FROM `{{dataset_ref}}.v_channel_daily` WHERE views_gained IS NOT NULL
),
x AS (
  SELECT
    l.d AS latest_report_date,
    SUM(IF(c.report_date > DATE_SUB(l.d, INTERVAL 7 DAY), c.views_gained, NULL)) AS views_last_7d,
    SUM(IF(c.report_date <= DATE_SUB(l.d, INTERVAL 7 DAY), c.views_gained, NULL)) AS views_prev_7d,
    SUM(IF(c.report_date > DATE_SUB(l.d, INTERVAL 7 DAY), c.subscribers_gained, NULL)) AS subscribers_last_7d,
    SUM(IF(c.report_date <= DATE_SUB(l.d, INTERVAL 7 DAY), c.subscribers_gained, NULL)) AS subscribers_prev_7d,
    SUM(IF(c.report_date > DATE_SUB(l.d, INTERVAL 7 DAY), c.uploads, NULL)) AS uploads_last_7d,
    SUM(IF(c.report_date <= DATE_SUB(l.d, INTERVAL 7 DAY), c.uploads, NULL)) AS uploads_prev_7d,
    SUM(IF(c.report_date > DATE_SUB(l.d, INTERVAL 7 DAY), c.engagement_gained, NULL)) AS engagement_last_7d,
    SUM(IF(c.report_date <= DATE_SUB(l.d, INTERVAL 7 DAY), c.engagement_gained, NULL)) AS engagement_prev_7d,
    COUNTIF(c.report_date > DATE_SUB(l.d, INTERVAL 7 DAY)) AS days_last_7d,
    COUNTIF(c.report_date <= DATE_SUB(l.d, INTERVAL 7 DAY)) AS days_prev_7d
  FROM `{{dataset_ref}}.v_channel_daily` AS c
  CROSS JOIN latest AS l
  WHERE c.views_gained IS NOT NULL
    AND c.report_date > DATE_SUB(l.d, INTERVAL 14 DAY)
  GROUP BY l.d
)
SELECT
  x.*,
  SAFE_DIVIDE(views_last_7d - views_prev_7d, views_prev_7d) AS views_change_pct,
  SAFE_DIVIDE(subscribers_last_7d - subscribers_prev_7d, ABS(subscribers_prev_7d)) AS subscribers_change_pct,
  SAFE_DIVIDE(engagement_last_7d - engagement_prev_7d, engagement_prev_7d) AS engagement_change_pct,
  CASE
    WHEN days_prev_7d < 7 THEN 'Needs 14 days of data'
    WHEN views_last_7d > views_prev_7d THEN 'Increasing'
    WHEN views_last_7d < views_prev_7d THEN 'Decreasing'
    ELSE 'Flat'
  END AS views_trend,
  CASE
    WHEN days_prev_7d < 7 THEN 'Needs 14 days of data'
    WHEN subscribers_last_7d > subscribers_prev_7d THEN 'Growing faster'
    WHEN subscribers_last_7d < subscribers_prev_7d THEN 'Growing slower'
    ELSE 'Same pace'
  END AS subscriber_trend
FROM x;
