-- Ready-made answers to the 16 business questions.
-- Run any block in the BigQuery console (the console's current project is used).
-- If BQ_DATASET is not youtube_derana, replace "youtube_derana." below.
-- Period used here: the last 7 report days. Change the DATE_SUB intervals for other periods.

-- =====================================================================================
-- 1-4. Channel performance for the period: views, subscribers, uploads, engagement
-- =====================================================================================
SELECT
  MIN(report_date) AS period_start,
  MAX(report_date) AS period_end,
  SUM(views_gained) AS total_views,
  SUM(subscribers_gained) AS net_subscribers,
  SUM(uploads) AS videos_uploaded,
  SUM(likes_gained) AS likes,
  SUM(comments_gained) AS comments,
  SUM(engagement_gained) AS engagement
FROM youtube_derana.v_channel_daily
WHERE views_gained IS NOT NULL
  AND report_date > DATE_SUB((SELECT MAX(report_date) FROM youtube_derana.v_channel_daily), INTERVAL 7 DAY);

-- =====================================================================================
-- 5-6. Views and subscriber growth vs the previous 7 days
-- =====================================================================================
SELECT
  views_last_7d, views_prev_7d, views_change_pct, views_trend,
  subscribers_last_7d, subscribers_prev_7d, subscribers_change_pct, subscriber_trend
FROM youtube_derana.v_rolling_comparison;

-- Calendar weeks
SELECT week_start, week_end, days_with_data, views_gained, views_wow_pct, views_trend,
       subscribers_gained, subscriber_trend
FROM youtube_derana.v_weekly_summary
ORDER BY week_start DESC;

-- =====================================================================================
-- 7. Best and worst days
-- =====================================================================================
(SELECT 'Best' AS rank_type, report_date, weekday, views_gained
 FROM youtube_derana.v_channel_daily WHERE views_gained IS NOT NULL
 ORDER BY views_gained DESC LIMIT 3)
UNION ALL
(SELECT 'Worst', report_date, weekday, views_gained
 FROM youtube_derana.v_channel_daily WHERE views_gained IS NOT NULL
 ORDER BY views_gained ASC LIMIT 3);

-- Average by weekday
SELECT weekday, weekday_num, COUNT(*) AS days, ROUND(AVG(views_gained)) AS avg_views
FROM youtube_derana.v_channel_daily
WHERE views_gained IS NOT NULL
GROUP BY weekday, weekday_num
ORDER BY avg_views DESC;

-- =====================================================================================
-- 8. Top-performing videos per window (uploaded in the window, ranked by views)
-- =====================================================================================
SELECT time_window, window_rank_views, video_title, video_format, category, view_count, like_count, comment_count
FROM youtube_derana.v_window_videos
WHERE window_rank_views <= 10
ORDER BY window_order, window_rank_views;

-- =====================================================================================
-- 9. Highest growth this week (views gained over the last 7 days, any upload date)
-- =====================================================================================
SELECT video_title, video_format, category, publish_date_local, views_gained_7d, growth_basis, view_count
FROM youtube_derana.v_videos_latest
ORDER BY views_gained_7d DESC
LIMIT 10;

-- =====================================================================================
-- 10. Underperformed (vs videos of the same format and age) or dropped (vs peers' normal decay)
-- =====================================================================================
SELECT video_title, video_format, age_bucket, view_count, peer_median_views,
       ROUND(performance_index, 2) AS performance_index, performance_label, momentum
FROM youtube_derana.v_videos_latest
WHERE performance_label LIKE '4)%' OR momentum LIKE 'Dropped%'
ORDER BY performance_index
LIMIT 25;

-- =====================================================================================
-- 11-12. Shorts vs long-form: reach and engagement
-- =====================================================================================
SELECT time_window, video_format, videos_uploaded, views, avg_views_per_video,
       likes, comments, ROUND(engagement_rate * 100, 2) AS engagement_rate_pct
FROM youtube_derana.v_window_summary
ORDER BY window_order, video_format;

-- Views gained per format over the last 7 days (includes older videos still getting views)
SELECT video_format, SUM(views_gained) AS views_gained, SUM(engagement_gained) AS engagement_gained,
       ROUND(SAFE_DIVIDE(SUM(engagement_gained), SUM(views_gained)) * 100, 2) AS engagement_rate_pct
FROM youtube_derana.v_breakdown_daily
WHERE report_date > DATE_SUB((SELECT MAX(report_date) FROM youtube_derana.v_breakdown_daily), INTERVAL 7 DAY)
GROUP BY video_format
ORDER BY views_gained DESC;

-- =====================================================================================
-- 13. Categories
-- 14. Programs (playlist / program mapping)
-- =====================================================================================
SELECT category, SUM(views_gained) AS views_gained,
       ROUND(100 * SUM(views_gained) / SUM(SUM(views_gained)) OVER (), 1) AS share_pct,
       SUM(engagement_gained) AS engagement_gained
FROM youtube_derana.v_breakdown_daily
WHERE report_date > DATE_SUB((SELECT MAX(report_date) FROM youtube_derana.v_breakdown_daily), INTERVAL 7 DAY)
GROUP BY category
ORDER BY views_gained DESC;

SELECT program, category, SUM(views_gained) AS views_gained,
       ROUND(100 * SUM(views_gained) / SUM(SUM(views_gained)) OVER (), 1) AS share_pct
FROM youtube_derana.v_breakdown_daily
WHERE report_date > DATE_SUB((SELECT MAX(report_date) FROM youtube_derana.v_breakdown_daily), INTERVAL 7 DAY)
GROUP BY program, category
ORDER BY views_gained DESC
LIMIT 15;

-- =====================================================================================
-- 15. Publishing time slots (videos from the last 28 days, at least 24 hours old)
-- =====================================================================================
SELECT time_slot, SUM(videos) AS videos, SUM(total_views) AS total_views,
       ROUND(SAFE_DIVIDE(SUM(total_views), SUM(videos))) AS avg_views_per_video
FROM youtube_derana.v_time_slots
GROUP BY time_slot, time_slot_order
ORDER BY time_slot_order;

-- =====================================================================================
-- 16. Spikes and drops
-- =====================================================================================
SELECT report_date, level, anomaly, video_title, ROUND(views) AS views,
       ROUND(baseline_views) AS baseline, ROUND(score, 2) AS score, score_type
FROM youtube_derana.v_anomalies
ORDER BY report_date DESC, level;
