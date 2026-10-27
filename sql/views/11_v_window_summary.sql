-- Upload counts and totals per time window and format (Q3, Q11, Q12).
CREATE OR REPLACE VIEW `{{dataset_ref}}.v_window_summary` AS
SELECT
  time_window,
  window_order,
  video_format,
  COUNT(*) AS videos_uploaded,
  SUM(view_count) AS views,
  SUM(like_count) AS likes,
  SUM(comment_count) AS comments,
  SUM(engagement) AS engagement,
  SAFE_DIVIDE(SUM(engagement), SUM(view_count)) AS engagement_rate,
  SAFE_DIVIDE(SUM(view_count), COUNT(*)) AS avg_views_per_video,
  APPROX_QUANTILES(view_count, 100)[OFFSET(50)] AS median_views_per_video
FROM `{{dataset_ref}}.v_window_videos`
GROUP BY time_window, window_order, video_format;
