-- Day-over-day change per video. views_gained = views added since the previous capture.
-- A video's first capture counts all its views as gained only if it was published after the
-- previous run (i.e. it is genuinely new); otherwise the first value is NULL (no baseline).
CREATE OR REPLACE VIEW `{{dataset_ref}}.v_video_daily` AS
WITH s AS (
  SELECT
    d.*,
    LAG(d.view_count) OVER w AS prev_views,
    LAG(d.like_count) OVER w AS prev_likes,
    LAG(d.comment_count) OVER w AS prev_comments,
    LAG(d.data_capture_date) OVER w AS prev_capture_date
  FROM `{{dataset_ref}}.v_report_daily` AS d
  WINDOW w AS (PARTITION BY d.video_id ORDER BY d.data_capture_date)
)
SELECT
  s.* EXCEPT (prev_views, prev_likes, prev_comments, prev_capture_date),
  CASE
    WHEN s.prev_views IS NOT NULL THEN s.view_count - s.prev_views
    WHEN r.prev_capture_ts IS NOT NULL AND s.publish_datetime_utc > r.prev_capture_ts THEN s.view_count
  END AS views_gained,
  CASE
    WHEN s.prev_likes IS NOT NULL THEN s.like_count - s.prev_likes
    WHEN r.prev_capture_ts IS NOT NULL AND s.publish_datetime_utc > r.prev_capture_ts THEN s.like_count
  END AS likes_gained,
  CASE
    WHEN s.prev_comments IS NOT NULL THEN s.comment_count - s.prev_comments
    WHEN r.prev_capture_ts IS NOT NULL AND s.publish_datetime_utc > r.prev_capture_ts THEN s.comment_count
  END AS comments_gained,
  DATE_DIFF(s.data_capture_date, s.prev_capture_date, DAY) AS days_since_prev_capture
FROM s
LEFT JOIN `{{dataset_ref}}.v_runs` AS r ON r.capture_date = s.data_capture_date;
