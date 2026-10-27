-- Publishing time slot vs performance (Q15). Uses videos at least 24 hours old so every
-- video has had a full first day.
CREATE OR REPLACE VIEW `{{dataset_ref}}.v_time_slots` AS
SELECT
  time_slot,
  time_slot_order,
  publish_hour_local,
  publish_weekday,
  publish_weekday_num,
  video_format,
  COUNT(*) AS videos,
  SUM(view_count) AS total_views,
  SAFE_DIVIDE(SUM(view_count), COUNT(*)) AS avg_views_per_video,
  APPROX_QUANTILES(view_count, 100)[OFFSET(50)] AS median_views_per_video,
  AVG(performance_index) AS avg_performance_index,
  SAFE_DIVIDE(SUM(engagement), SUM(view_count)) AS engagement_rate
FROM `{{dataset_ref}}.v_videos_latest`
WHERE age_hours >= 24 AND in_last_28d
GROUP BY time_slot, time_slot_order, publish_hour_local, publish_weekday, publish_weekday_num, video_format;
