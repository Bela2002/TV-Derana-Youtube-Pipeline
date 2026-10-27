-- REQUIRED DAILY REPORTING DATASET: one row per video per daily capture.
CREATE OR REPLACE VIEW `{{dataset_ref}}.v_report_daily` AS
SELECT
  s.video_id,
  v.title AS video_title,
  COALESCE(v.channel_title, c.channel_title) AS channel_name,
  pp.primary_playlist_id AS playlist_id,
  pp.primary_playlist_title AS playlist_name,
  s.channel_id,
  v.published_at AS publish_datetime_utc,
  DATETIME(v.published_at, '{{timezone}}') AS publish_datetime_local,
  IF(
    v.duration_seconds IS NULL, NULL,
    FORMAT('%d:%02d:%02d', DIV(v.duration_seconds, 3600), DIV(MOD(v.duration_seconds, 3600), 60), MOD(v.duration_seconds, 60))
  ) AS video_duration,
  v.duration_seconds,
  s.like_count,
  s.view_count,
  s.comment_count,
  s.capture_date AS data_capture_date,
  s.capture_ts AS data_capture_timestamp_utc,
  r.report_date,
  v.video_format,
  v.format_method,
  cat.category,
  cat.program,
  pp.all_playlist_ids,
  pp.all_playlist_titles,
  IFNULL(pp.playlist_count, 0) AS playlist_count,
  CONCAT('https://www.youtube.com/watch?v=', s.video_id) AS video_url
FROM `{{dataset_ref}}.video_snapshots` AS s
JOIN `{{dataset_ref}}.videos` AS v ON v.video_id = s.video_id
LEFT JOIN `{{dataset_ref}}.channels` AS c ON c.channel_id = s.channel_id
LEFT JOIN `{{dataset_ref}}.v_runs` AS r ON r.capture_date = s.capture_date
LEFT JOIN `{{dataset_ref}}.v_video_playlist_primary` AS pp ON pp.video_id = s.video_id
LEFT JOIN `{{dataset_ref}}.v_video_category` AS cat ON cat.video_id = s.video_id;
