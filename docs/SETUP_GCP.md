# Google Cloud setup

This guide sets up the complete pipeline: BigQuery storage, a Cloud Run service built straight from the source code (no Dockerfile), a Cloud Scheduler job that runs it every day, and the YouTube API key kept in Secret Manager.

Time: about 15 minutes. Cost: within the Google Cloud free tier for this workload (see the end of this page).

---

## 1. Prerequisites

1. A Google account.
2. A Google Cloud project with billing enabled:
   * Console → <https://console.cloud.google.com/projectcreate> → name it (e.g. `yt-performance`) → **Create**.
   * Billing → <https://console.cloud.google.com/billing/linkedaccount> → link a billing account. New accounts get free trial credit; this workload stays within the always-free tier.
   * Note the **Project ID** (shown on the dashboard, e.g. `yt-performance-123456`).
3. Owner (or Editor + Security Admin) role on the project.

No local installs are needed when using Cloud Shell. To run from a local machine instead, install the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install), run `gcloud auth login`, and use a bash shell (macOS/Linux terminal, or WSL / Git Bash on Windows).

## 2. Open Cloud Shell and get the code

1. Open <https://shell.cloud.google.com> (or the `>_` icon in the console).
2. Clone the repository:

   ```bash
   git clone <this-repository-url> tv-derana-youtube-pipeline
   cd tv-derana-youtube-pipeline
   ```

   Alternatively upload a ZIP of the repository with Cloud Shell's **⋮ → Upload**, then `unzip <file>.zip && cd <folder>`.

## 3. Configure

```bash
cp .env.example .env
nano .env
```

Set `PROJECT_ID`. Everything else has working defaults:

| Setting | Default | Meaning |
|---------|---------|---------|
| `PROJECT_ID` | – | Google Cloud project ID (required) |
| `REGION` | `us-central1` | Region for Cloud Run and Cloud Scheduler |
| `BQ_LOCATION` | `US` | BigQuery dataset location, e.g. `US`, `EU`, `asia-south1` (fixed after creation) |
| `BQ_DATASET` | `youtube_derana` | BigQuery dataset name |
| `YOUTUBE_API_KEY` | empty | Empty = setup creates a key restricted to YouTube Data API v3 |
| `CHANNEL_HANDLE` | `@tvderanaofficial` | Channel handle to track |
| `CHANNEL_ID` | empty | Channel ID (`UC...`); overrides the handle when set |
| `SCHEDULE` | `5 0 * * *` | Cron schedule; default 00:05 every day |
| `SCHEDULE_TIMEZONE` | `Asia/Colombo` | Time zone of the schedule |
| `LOOKBACK_DAYS` | `90` | Videos published in this many days are snapshotted daily |
| `SHORTS_DETECTION` | `playlist,url,duration` | Order of Shorts detection methods |
| `SHORTS_MAX_SECONDS` | `180` | Longest possible Short |
| `REPORT_TIMEZONE` | `Asia/Colombo` | Time zone for publish hour, time slots and report dates |
| `PLAYLIST_PAGE_BUDGET` | `3000` | Max API pages spent on playlist scanning per run |
| `PLAYLIST_MAX_PAGES` | `4` | Pages per playlist when the budget is exceeded |
| `PLAYLIST_RESCAN_DAYS` | `7` | Re-read every playlist at least this often |
| `SERVICE_NAME`, `SCHEDULER_JOB`, `SECRET_NAME` | see file | Resource names |

Save with **Ctrl+O**, **Enter**, exit with **Ctrl+X**.

## 4. Run the setup

```bash
bash scripts/setup_gcp.sh
```

What it does (safe to re-run; existing resources are reused):

1. Checks billing and selects the project.
2. Enables the APIs: Cloud Run, Cloud Build, Artifact Registry, Cloud Scheduler, BigQuery, Secret Manager, YouTube Data API v3, API Keys, IAM.
3. Creates two service accounts:
   * `<SERVICE_NAME>-run` – identity of the pipeline: BigQuery Job User on the project (run jobs, no data access), Data Editor on the pipeline's dataset only, and read access to the API key secret only.
   * `<SERVICE_NAME>-sched` – identity of Cloud Scheduler: may only invoke the Cloud Run service.
4. Grants **Cloud Run Builder** to the default compute service account, which Cloud Build uses for source deployments.
5. Creates a YouTube API key restricted to YouTube Data API v3 (or uses the one from `.env`) and stores it in Secret Manager.
6. Creates the BigQuery dataset in `BQ_LOCATION` and gives the pipeline account edit access to that dataset only.
7. Runs `scripts/deploy.sh`:
   * `gcloud run deploy --source .` – Cloud Build packages the code with the Python buildpack (`requirements.txt`, `Procfile`, `.python-version`); no Dockerfile.
   * Private service (no public access), one instance at a time, 30-minute timeout, API key injected from Secret Manager.
   * Creates/updates the Cloud Scheduler job calling `POST /run` with an OIDC token of the scheduler account, retrying up to twice on failure (not on YouTube quota errors, which cannot succeed until the quota resets).
8. Calls the service once so data appears immediately and prints the result.

The first run creates all tables and views. Expected output ends with something like:

```json
{
  "status": "success",
  "channel": "TV Derana",
  "videos_tracked": 1800,
  "new_videos": 1800,
  "playlists": 650,
  "api_units_used": 1400
}
```

## 5. Verify

* **BigQuery**: <https://console.cloud.google.com/bigquery> → your project → `youtube_derana`. Tables: `channels`, `channel_snapshots`, `videos`, `video_snapshots`, `playlists`, `video_playlists`, `category_rules`, `pipeline_runs`; views `v_*`. Try:

  ```sql
  SELECT * FROM youtube_derana.v_report_daily ORDER BY view_count DESC LIMIT 20;
  ```

* **Cloud Scheduler**: <https://console.cloud.google.com/cloudscheduler> → the job shows the next run time. **Force run** triggers it manually.
* **Cloud Run**: <https://console.cloud.google.com/run> → service → **Logs** shows each run.
* `sql/queries/questions.sql` has ready-made queries for all 16 business questions.

Then build the dashboard: [DASHBOARD.md](DASHBOARD.md).

---

## Operating the pipeline

| Task | How |
|------|-----|
| Run now | `bash scripts/run_now.sh`, or Cloud Scheduler → **Force run** |
| Change schedule | Edit `SCHEDULE` / `SCHEDULE_TIMEZONE` in `.env`, then `bash scripts/deploy.sh` |
| Change category rules | Edit `config/category_rules.json`, check with `python3 scripts/review_playlists.py`, then `bash scripts/deploy.sh` |
| Change code or settings | Edit, run `pytest` (optional), then `bash scripts/deploy.sh` |
| Replace the API key | Put the new key in `YOUTUBE_API_KEY` in `.env` and re-run `bash scripts/setup_gcp.sh`; the next run picks it up |
| Pause collection | `gcloud scheduler jobs pause yt-derana-daily --location us-central1` (`resume` to restart) |
| Run history | `SELECT * FROM youtube_derana.pipeline_runs ORDER BY started_at DESC` |
| Remove everything | `bash scripts/teardown_gcp.sh` (`--delete-data` also drops the dataset) |

Running more than once on the same UTC day is safe: that day's snapshot is replaced, not duplicated.

### Failure alerts (optional)

Cloud Run → service → **Logs** → create a log-based alert on `severity>=ERROR`, or Monitoring → Alerting → policy on the Cloud Scheduler job's failed attempts. The dashboard's "Last updated" tile (`v_data_freshness`) also shows the last run status.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `billing is not enabled` | Link a billing account to the project and re-run setup. |
| Build fails with a permission error on `...-compute@developer.gserviceaccount.com` | Grant it **Cloud Run Builder**: `gcloud projects add-iam-policy-binding PROJECT_ID --member=serviceAccount:PROJECT_NUMBER-compute@developer.gserviceaccount.com --role=roles/run.builder`, wait two minutes, run `bash scripts/deploy.sh`. If the organisation disabled the default compute account, deploy with a custom build account: add `--build-service-account=projects/PROJECT_ID/serviceAccounts/<sa-email>` to the `gcloud run deploy` command in `scripts/deploy.sh` and give that account `roles/run.builder`. |
| `Policy ... constraints/iam.allowedPolicyMemberDomains` or similar organisation policy errors | Use a project outside the restricted organisation, or ask the organisation admin. |
| Service account "does not exist" right after creation | IAM propagation delay; re-run the script. |
| `run_now.sh` returns 403 | The account running the script needs `roles/run.invoker` on the service (project Owners have it). |
| Run returns `"status": "quota_exceeded"` | Daily YouTube quota (10,000 units) used up. It resets at midnight Pacific time and the next scheduled run collects normally. If it keeps happening, lower `LOOKBACK_DAYS` or `PLAYLIST_PAGE_BUDGET`. |
| `Access Denied` on BigQuery in the Cloud Run logs | Re-run `bash scripts/setup_gcp.sh`; it re-applies the dataset access. If `BQ_DATASET` was changed, the new dataset needs the same access, which the script grants. |
| `Channel not found` | Check `CHANNEL_HANDLE` (with `@`) or set `CHANNEL_ID`. |
| API key errors (`API_KEY_INVALID`, `accessNotConfigured`) | Confirm YouTube Data API v3 is enabled and the key is restricted to it, not to another API. New keys can take a few minutes to work. |
| `api-keys create` fails | Create a key manually: Console → APIs & Services → Credentials → **Create credentials → API key** → restrict to YouTube Data API v3; put it in `.env` as `YOUTUBE_API_KEY` and re-run setup. |
| Scheduler job shows failed runs | Cloud Run logs: `gcloud run services logs read yt-derana-pipeline --region us-central1 --limit 100`. |
| BigQuery `Not found: Dataset` in a different location | `BQ_LOCATION` must match the dataset's location. A dataset cannot be moved; delete it (`teardown --delete-data`) or set `BQ_DATASET` to a new name. |

---

## Free tier notes

At the time of writing, the always-free tier per billing account includes roughly: Cloud Run 2 million requests and 180,000 vCPU-seconds per month; Cloud Scheduler 3 jobs; BigQuery 10 GiB storage and 1 TiB of queries per month; Secret Manager 6 active secret versions and 10,000 access operations per month; plus build minutes in Cloud Build and 0.5 GB in Artifact Registry. One daily run of a few minutes and a few MB per day of snapshots use a small fraction of this. Free tier details change, so check <https://cloud.google.com/free> and set a budget alert (Billing → Budgets & alerts) for peace of mind.

Each deployment stores a container image in Artifact Registry (`cloud-run-source-deploy`). To stay under 0.5 GB, delete old images there occasionally or add a cleanup policy to the repository.
