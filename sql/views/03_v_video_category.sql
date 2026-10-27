-- Category / program per video using config/category_rules.json (loaded into category_rules).
-- Text matched: "<video title> | <all playlist names>", lowercased. Lowest priority number wins.
CREATE OR REPLACE VIEW `{{dataset_ref}}.v_video_category` AS
WITH base AS (
  SELECT
    v.video_id,
    pp.primary_playlist_title,
    LOWER(CONCAT(IFNULL(v.title, ''), ' | ', IFNULL(pp.all_playlist_titles, ''))) AS match_text
  FROM `{{dataset_ref}}.videos` AS v
  LEFT JOIN `{{dataset_ref}}.v_video_playlist_primary` AS pp ON pp.video_id = v.video_id
),
matches AS (
  SELECT
    b.video_id,
    ARRAY_AGG(STRUCT(r.category, r.program, r.priority) ORDER BY r.priority LIMIT 1)[OFFSET(0)] AS best
  FROM base AS b
  CROSS JOIN `{{dataset_ref}}.category_rules` AS r
  WHERE REGEXP_CONTAINS(b.match_text, r.pattern)
  GROUP BY b.video_id
)
SELECT
  b.video_id,
  IFNULL(m.best.category, '{{default_category}}') AS category,
  COALESCE(m.best.program, b.primary_playlist_title, 'Unassigned (no playlist)') AS program,
  m.best.priority AS matched_rule_priority
FROM base AS b
LEFT JOIN matches AS m ON m.video_id = b.video_id;
