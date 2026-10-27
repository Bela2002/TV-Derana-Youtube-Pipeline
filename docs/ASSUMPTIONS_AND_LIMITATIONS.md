# Assumptions and limitations

## Assumptions

1. **One channel, public data.** The pipeline tracks one channel (default TV Derana, `@tvderanaofficial`) using an API key, so it only sees what the public YouTube Data API v3 exposes. No channel-owner login (OAuth) is used.
2. **Daily snapshots are the source of truth for change.** The Data API returns lifetime totals only. Daily views, likes, comments and subscriber changes are calculated as the difference between consecutive daily snapshots.
3. **Tracked videos.** Every run snapshots all videos published within `LOOKBACK_DAYS` (default 90). Older videos are not snapshotted, but their views are still included in the channel-level "views gained" (lifetime channel views).
4. **Time windows** ("last 24 hours / 7 days / 28 days") are based on publish time and measured back from the latest capture, so dashboard numbers match the data even if a run is late.
5. **"Top performing" means most views** for videos published inside the window, as the brief specifies. Growth and peer benchmarks add context for videos of different ages.
6. **Time zone.** Capture date and timestamp are stored in UTC (as required). Publish hour, time slots, weekdays and report dates use Sri Lanka time (`Asia/Colombo`). The default schedule (00:05 Sri Lanka time) makes each run cover the previous local day.
7. **Shorts.** A video is a Short when it appears in the channel's auto-generated Shorts playlist; otherwise the `youtube.com/shorts/<id>` page check is used; duration ≤ 180 seconds is the last fallback. Videos longer than 180 seconds are always long-form.
8. **Categories and programs** come from `config/category_rules.json`: keyword rules on video titles and playlist names. They map to News, Dream Star, Reality shows, Entertainment and Sports; unmatched videos are `Other`. Dream Star is kept separate from other reality shows as requested.
9. **Main playlist.** A video can sit in several playlists. The report shows one main playlist (preferring a program playlist), and lists all of them in `all_playlist_titles`, so totals are never double counted.

## Limitations

| Area | Limitation | Effect / mitigation |
|------|-----------|---------------------|
| Shares | Not available in the YouTube Data API v3 (only in the YouTube Analytics API, which needs the channel owner's OAuth consent). | Engagement = likes + comments. The schema can be extended with Analytics API data if owner access is granted. |
| Subscribers | YouTube publishes subscriber counts rounded to three significant figures (e.g. 6.57M), so for a channel this size the count moves in steps of 10,000. | Daily subscriber change is often 0 or ±10,000. Weekly and monthly views of the trend are more reliable than daily values. |
| Audience time | The public API has no "views by hour watched" data. | Q15 is answered with **publishing** time slots (which upload times lead to the most views), not viewing times. |
| History | No historical backfill of daily changes is possible; the API has no past snapshots. | Daily deltas start on day 2, week-over-week after 8-14 days, anomaly detection after 8 days. Lifetime totals are available from day 1. |
| First-day views | A new video's views before its first capture are counted as gained only if it was published after the previous run. | Videos added by widening `LOOKBACK_DAYS` get a baseline instead of an inflated first-day value. |
| Shorts detection | The Shorts playlist (`UUSH…`) and the `/shorts/` URL behaviour are not part of the documented API and may change. | Automatic fallback to the next method; `format_method` shows which one decided. |
| Categories | Keyword rules can misclassify videos with unusual titles or no playlist. | Review with `scripts/review_playlists.py`; rules apply retroactively. |
| Playlists | Very large channels may need more playlist pages than the per-run budget. Playlists are re-read only when their item count changes or weekly. | Links accumulate over runs; the first run may need a few days to map every playlist. |
| Hidden counts | Likes or comments can be hidden or disabled. | Stored as NULL (not 0); sums ignore them. |
| Deleted / private videos | They disappear from the API. | They stop appearing in the latest views; past snapshots are kept. |
| Quota | 10,000 units per day per project. A normal run uses a few hundred to ~3,000. | Quota errors stop the run without writing partial data. The run is logged as `quota_exceeded` (ERROR in Cloud Logging, row in `pipeline_runs`) and is not retried, because retries would fail until the quota resets; the next scheduled run collects again. Other errors are retried up to twice by the scheduler. |
| Anomaly thresholds | Fixed rules (z-score ±2 over 14 days; video 3× own average). | Adjust in `sql/views/06_v_channel_daily.sql` and `14_v_anomalies.sql`. |
| Looker Studio | Report layout is built in the Looker Studio UI (no public API to create charts). | `docs/DASHBOARD.md` gives every chart, field and setting; `scripts/looker_link.py` pre-connects BigQuery. |
| Freshness | Data updates once a day. | Looker Studio cache set to 4-12 hours is enough. |

## Security

* The YouTube API key is stored only in Secret Manager and injected into Cloud Run at runtime; `.env` is excluded from git and from uploads, and error messages never include the key.
* The key created by setup can only call YouTube Data API v3.
* The Cloud Run service is private: only the scheduler's service account (and project owners) can call it, using signed OIDC tokens.
* The pipeline's service account can run BigQuery jobs (Job User on the project) but can read and write data **only in its own dataset** (dataset-level Data Editor). It can read only its own secret.

## Cost

All services used have always-free allowances that this workload stays within (one short Cloud Run request per day, one Cloud Scheduler job, a few MB of BigQuery storage per day, batch load jobs which are free, and small queries). Cloud Run and Cloud Scheduler still require a billing account to be linked. A budget alert is recommended.
