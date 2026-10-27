# Looker Studio dashboard

The dashboard reads the BigQuery **views** created by the pipeline. Nothing is copied or exported, so the dashboard is always as fresh as the last daily run.

Build time: about 45 minutes the first time. Run the pipeline at least once before starting (the views need data).

> Trend questions (views gained, week-over-week, anomalies) need several days of snapshots. Day 1 shows totals; daily changes appear from day 2; week-over-week from day 8 (calendar weeks) or day 14 (rolling 7 vs 7); anomaly detection from day 8.

---

## 1. Create the report

1. In Cloud Shell (or locally) run:

   ```bash
   python3 scripts/looker_link.py
   ```

2. Open the printed link while signed in with the Google account that owns the project. Looker Studio opens a new report connected to `v_window_videos`. Click **Edit and share** → **Acknowledge and save** → **Add to report**.
   *Without the script:* go to <https://lookerstudio.google.com> → **Blank report** → **BigQuery** → **My projects** → your project → `youtube_derana` → `v_window_videos` → **Add**.
3. Add the other data sources: **Add data** → **BigQuery** → **My projects** → your project → `youtube_derana` → pick the view → **Add**. Repeat for:

   | Data source | Used for |
   |-------------|----------|
   | `v_channel_daily` | Channel KPIs, daily trends, best/worst days, anomalies (Q1-Q7, Q16) |
   | `v_rolling_comparison` | Last 7 days vs previous 7 days (Q5, Q6) |
   | `v_weekly_summary` | Calendar week-over-week table (Q5, Q6) |
   | `v_window_videos` | Uploads and top videos for 24h / 7d / 28d (assessment requirements, Q8) |
   | `v_window_summary` | Upload counts per window, Shorts vs long-form (Q3, Q11, Q12) |
   | `v_videos_latest` | Growth, underperformers, drops (Q8-Q10) |
   | `v_breakdown_daily` | Format / category / program views over any date range (Q11-Q14) |
   | `v_time_slots` | Publishing time slots (Q15) |
   | `v_anomalies` | Spike and drop list (Q16) |
   | `v_data_freshness` | "Last updated" tile |

4. Data freshness: **Resource** → **Manage added data sources** → **Edit** on each source → **Data freshness** (top bar) → **Every 4 hours** (data changes once a day, so anything up to 12 hours is fine).
5. In each data source, check field types: fields ending in `_pct` and `engagement_rate` → **Percent**; `report_date`, `publish_date_local` → **Date**.

### Report-wide settings

* **Theme and layout** → pick a theme, canvas 1200 × 1600 or larger.
* Add a **Date range control** to every page (Insert → Date range control), default **Last 28 days**.
* Every chart has a **Date range dimension** in its Setup panel. Set it explicitly as listed below so the date control filters the right date:
  * `v_channel_daily`, `v_breakdown_daily` → `report_date`
  * `v_videos_latest` → `publish_date_local` (filters by upload date)
  * `v_window_videos`, `v_window_summary`, `v_time_slots`, `v_rolling_comparison`, `v_weekly_summary`, `v_data_freshness`, `v_anomalies` → leave empty; these are already limited to fixed windows relative to the latest run (for `v_anomalies` set `report_date` if the list should follow the date control)
* Single channel: no channel filter is needed. `channel_name` is available in every video-level source if one is wanted.

---

## Page 1 – Overview ("What happened?", Q1-Q6)

| Element | Source | Setup |
|---------|--------|-------|
| Scorecard **Total views** (Q1) | `v_channel_daily` | Metric `views_gained` (SUM). Comparison date range: **Previous period** → shows the change vs the previous period (Q5). |
| Scorecard **Net subscribers** (Q2) | `v_channel_daily` | Metric `subscribers_gained` (SUM), comparison **Previous period** (Q6). |
| Scorecard **Videos uploaded** (Q3) | `v_channel_daily` | Metric `uploads` (SUM). |
| Scorecards **Likes**, **Comments**, **Engagement** (Q4) | `v_channel_daily` | `likes_gained`, `comments_gained`, `engagement_gained` (SUM). |
| Text box **Shares** | – | "Shares: not provided by YouTube Data API v3" (see limitations). |
| Table **Last 7 days vs previous 7** (Q5, Q6) | `v_rolling_comparison` | Dimensions `views_trend`, `subscriber_trend`; metrics `views_last_7d`, `views_change_pct`, `subscribers_last_7d`, `subscribers_change_pct`. |
| Time series **Daily views** | `v_channel_daily` | Dimension `report_date`; metrics `views_gained`, `views_7d_moving_avg`. |
| Column chart **Daily subscribers** | `v_channel_daily` | Dimension `report_date`; metric `subscribers_gained`. |
| Table **Week over week** | `v_weekly_summary` | Dimensions `week_start`, `views_trend`, `subscriber_trend`; metrics `views_gained`, `views_wow_pct`, `subscribers_gained`, `uploads`, `days_with_data`. Sort `week_start` descending. |
| Text **Last updated** | `v_data_freshness` | Table with `latest_capture_local`, `last_run_status`, `videos_tracked_latest`. |

## Page 2 – Uploads & top videos (assessment requirements)

| Element | Source | Setup |
|---------|--------|-------|
| Column chart **Uploads per window** | `v_window_summary` | Dimension `time_window` (sort by `window_order` ascending), breakdown `video_format`, metric `videos_uploaded`. Shows the 24h / 7d / 28d counts at once. |
| Table **Uploaded in the last 24 hours** | `v_window_videos` | Filter: `time_window` = `Last 24 hours`. Dimensions `publish_datetime_local`, `video_title`, `video_format`, `category`, `video_duration`, `video_url`; metrics `view_count`, `like_count`, `comment_count`, `engagement_rate`. Sort `publish_datetime_local` descending. |
| Drop-down control **Time window** | `v_window_videos` | Control field `time_window`, single select, default `Last 7 days`. |
| Table **Top videos (sortable)** | `v_window_videos` | Dimensions `window_rank_views`, `video_title`, `video_format`, `category`, `publish_date_local`; metrics `view_count`, `like_count`, `comment_count`. Default sort `view_count` descending; **Style → Table header: sort enabled** lets viewers click column headers to sort by views, likes or comments. Rows per page: 25. |
| Bar chart **Top 10 by views** | `v_window_videos` | Dimension `video_title`, metric `view_count`, sort descending, 10 bars. Follows the time window control. |

## Page 3 – Video performance (Q8-Q10)

| Element | Source | Setup |
|---------|--------|-------|
| Table **Top-performing videos** (Q8) | `v_videos_latest` | Date range dimension `publish_date_local`. Dimensions `video_title`, `video_format`, `category`, `program`; metrics `view_count`, `engagement_rate`, `performance_index`. Sort `view_count` desc. |
| Table **Highest growth this week** (Q9) | `v_videos_latest` | No date range dimension. Dimensions `video_title`, `publish_date_local`, `growth_basis`; metrics `views_gained_7d`, `growth_wow_pct`. Sort `views_gained_7d` desc, 15 rows. |
| Table **Underperformed or dropped** (Q10) | `v_videos_latest` | Filter (Include, OR): `performance_label` contains `Underperformer` **or** `momentum` starts with `Dropped`. Dimensions `video_title`, `video_format`, `age_bucket`, `performance_label`, `momentum`; metrics `view_count`, `peer_median_views`, `performance_index`. Sort `performance_index` ascending. |
| Drop-down controls | `v_videos_latest` | `performance_label`, `video_format`, `category`. |

How to read it: `performance_index` = views ÷ median views of videos with the same format and the same age (e.g. Shorts aged 3-7 days). Below 0.5 is an underperformer. `momentum` compares a video's last 7 days with its previous 7 days against how similar videos normally decline, so a normal post-launch decline is not reported as a drop.

## Page 4 – Formats, categories, programs (Q11-Q14)

| Element | Source | Setup |
|---------|--------|-------|
| Donut **Views by format** (Q11) | `v_breakdown_daily` | Dimension `video_format`, metric `views_gained`. |
| Calculated field `Engagement rate` | `v_breakdown_daily` | Add field: `SUM(engagement_gained) / SUM(views_gained)`, type Percent. |
| Bar **Engagement rate by format** (Q12) | `v_breakdown_daily` | Dimension `video_format`, metric `Engagement rate`. |
| Table **Format by window** (Q11, Q12) | `v_window_summary` | Dimensions `time_window`, `video_format`; metrics `videos_uploaded`, `views`, `avg_views_per_video`, `engagement_rate`. |
| Bar **Views by category** (Q13) | `v_breakdown_daily` | Dimension `category`, metric `views_gained`, sort desc. |
| Time series **Category trend** | `v_breakdown_daily` | Dimension `report_date`, breakdown `category`, metric `views_gained`. |
| Table **Top programs** (Q14) | `v_breakdown_daily` | Dimensions `program`, `category`; metrics `views_gained`, `engagement_gained`, `active_videos`. Sort `views_gained` desc, 15 rows. Add a **Percent of total** comparison on `views_gained` (metric options → Comparison calculation → Percent of total). |

## Page 5 – Timing & anomalies (Q7, Q15, Q16)

| Element | Source | Setup |
|---------|--------|-------|
| Table **Best days** (Q7) | `v_channel_daily` | Dimensions `report_date`, `weekday`; metric `views_gained`; sort desc; 5 rows. |
| Table **Worst days** (Q7) | `v_channel_daily` | Same, sort ascending; filter `views_gained` is not null. |
| Bar **Average views by weekday** | `v_channel_daily` | Dimension `weekday`; metric `views_gained` with aggregation **Average**; sort by `weekday_num` ascending (add it as a sort field with aggregation Min). |
| Calculated field `Avg views per video` | `v_time_slots` | `SUM(total_views) / SUM(videos)`. |
| Bar **Views by publishing time slot** (Q15) | `v_time_slots` | Dimension `time_slot` (sort by `time_slot_order`), metric `Avg views per video`, breakdown `video_format` optional. |
| Pivot table heatmap **Weekday × hour** | `v_time_slots` | Row `publish_weekday`, column `publish_hour_local`, metric `Avg views per video`, Style → heatmap. |
| Time series **Spikes and drops** (Q16) | `v_channel_daily` | Dimension `report_date`; metrics `views_per_day`, `baseline_views_per_day`. Add `anomaly_flag` as a table beside it or as a chart filter. |
| Table **Anomaly log** (Q16) | `v_anomalies` | Dimensions `report_date`, `level`, `anomaly`, `video_title`, `score_type`; metrics `views`, `baseline_views`, `score`. Sort `report_date` desc. |

---

## Share the dashboard

1. **Share** → **Manage access** → add people, or **Anyone with the link can view**.
2. Data sources use **Owner's credentials** by default, so viewers do not need BigQuery access. Keep it that way (Resource → Manage added data sources → Edit → Data credentials).
3. For the submission, either share the link or use **File → Download → PDF** for screenshots.

## If something looks empty

* Run `bash scripts/run_now.sh` and refresh (**View → Refresh data** in edit mode, or the ⋮ menu → **Refresh data** in view mode).
* "Building baseline", "Not enough history" and empty week-over-week values are expected during the first days.
* A chart showing "Configuration incomplete" usually has the wrong date range dimension; set it as listed above.
