-- One row per video: its main playlist plus the list of every playlist it belongs to.
-- Main playlist = a playlist whose name matches a category rule, then the most specific
-- (fewest items), then alphabetical.
CREATE OR REPLACE VIEW `{{dataset_ref}}.v_video_playlist_primary` AS
WITH rule_match AS (
  SELECT
    p.playlist_id,
    LOGICAL_OR(REGEXP_CONTAINS(LOWER(IFNULL(p.playlist_title, '')), r.pattern)) AS matches_rule
  FROM `{{dataset_ref}}.playlists` AS p
  CROSS JOIN `{{dataset_ref}}.category_rules` AS r
  GROUP BY p.playlist_id
),
links AS (
  SELECT
    vp.video_id,
    p.playlist_id,
    p.playlist_title,
    IFNULL(p.item_count, 999999999) AS item_count,
    IFNULL(m.matches_rule, FALSE) AS matches_rule
  FROM `{{dataset_ref}}.video_playlists` AS vp
  JOIN `{{dataset_ref}}.playlists` AS p ON p.playlist_id = vp.playlist_id
  LEFT JOIN rule_match AS m ON m.playlist_id = p.playlist_id
),
agg AS (
  SELECT
    video_id,
    ARRAY_AGG(
      STRUCT(playlist_id, playlist_title)
      ORDER BY matches_rule DESC, item_count ASC, playlist_title ASC
      LIMIT 1
    )[OFFSET(0)] AS main,
    STRING_AGG(playlist_id, ', ' ORDER BY playlist_title) AS all_playlist_ids,
    STRING_AGG(playlist_title, ' | ' ORDER BY playlist_title) AS all_playlist_titles,
    COUNT(*) AS playlist_count
  FROM links
  GROUP BY video_id
)
SELECT
  video_id,
  main.playlist_id AS primary_playlist_id,
  main.playlist_title AS primary_playlist_title,
  all_playlist_ids,
  all_playlist_titles,
  playlist_count
FROM agg;
