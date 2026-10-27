-- Daily views/engagement gained, split by format, category and program (Q11-Q14 over any date range).
CREATE OR REPLACE VIEW `{{dataset_ref}}.v_breakdown_daily` AS
SELECT
  report_date,
  data_capture_date,
  video_format,
  category,
  program,
  COUNT(DISTINCT video_id) AS active_videos,
  COUNT(DISTINCT IF(views_gained > 0, video_id, NULL)) AS videos_with_new_views,
  SUM(views_gained) AS views_gained,
  SUM(likes_gained) AS likes_gained,
  SUM(comments_gained) AS comments_gained,
  SUM(IFNULL(likes_gained, 0) + IFNULL(comments_gained, 0)) AS engagement_gained
FROM `{{dataset_ref}}.v_video_daily`
WHERE views_gained IS NOT NULL
GROUP BY report_date, data_capture_date, video_format, category, program;
