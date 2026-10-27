-- Videos repeated once per time window they belong to. Use the "time_window" field as a
-- dropdown filter; tables then show uploads / top videos for that window and sort by any metric.
CREATE OR REPLACE VIEW `{{dataset_ref}}.v_window_videos` AS
SELECT
  w.time_window,
  w.window_order,
  v.*,
  RANK() OVER (PARTITION BY w.time_window ORDER BY v.view_count DESC) AS window_rank_views,
  RANK() OVER (PARTITION BY w.time_window ORDER BY v.like_count DESC) AS window_rank_likes,
  RANK() OVER (PARTITION BY w.time_window ORDER BY v.comment_count DESC) AS window_rank_comments
FROM `{{dataset_ref}}.v_videos_latest` AS v
CROSS JOIN UNNEST([
  STRUCT('Last 24 hours' AS time_window, 1 AS window_order),
  STRUCT('Last 7 days' AS time_window, 2 AS window_order),
  STRUCT('Last 28 days' AS time_window, 3 AS window_order)
]) AS w
WHERE (w.window_order = 1 AND v.in_last_24h)
   OR (w.window_order = 2 AND v.in_last_7d)
   OR (w.window_order = 3 AND v.in_last_28d);
