#!/usr/bin/env bash
# Shared settings for the setup scripts. Reads .env from the repository root.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ ! -f .env ]]; then
  echo "ERROR: .env not found. Run: cp .env.example .env  and set PROJECT_ID." >&2
  exit 1
fi
set -a
# shellcheck disable=SC1091
source .env
set +a

: "${PROJECT_ID:?PROJECT_ID is empty in .env}"
if [[ "$PROJECT_ID" == "your-gcp-project-id" ]]; then
  echo "ERROR: set PROJECT_ID in .env to your Google Cloud project ID." >&2
  exit 1
fi

REGION="${REGION:-us-central1}"
BQ_LOCATION="${BQ_LOCATION:-US}"
BQ_DATASET="${BQ_DATASET:-youtube_derana}"
CHANNEL_HANDLE="${CHANNEL_HANDLE:-@tvderanaofficial}"
CHANNEL_ID="${CHANNEL_ID:-}"
SCHEDULE="${SCHEDULE:-5 0 * * *}"
SCHEDULE_TIMEZONE="${SCHEDULE_TIMEZONE:-Asia/Colombo}"
LOOKBACK_DAYS="${LOOKBACK_DAYS:-90}"
SHORTS_DETECTION="${SHORTS_DETECTION:-playlist,url,duration}"
SHORTS_MAX_SECONDS="${SHORTS_MAX_SECONDS:-180}"
REPORT_TIMEZONE="${REPORT_TIMEZONE:-Asia/Colombo}"
PLAYLIST_PAGE_BUDGET="${PLAYLIST_PAGE_BUDGET:-3000}"
PLAYLIST_MAX_PAGES="${PLAYLIST_MAX_PAGES:-4}"
PLAYLIST_RESCAN_DAYS="${PLAYLIST_RESCAN_DAYS:-7}"
SERVICE_NAME="${SERVICE_NAME:-yt-derana-pipeline}"
SCHEDULER_JOB="${SCHEDULER_JOB:-yt-derana-daily}"
SECRET_NAME="${SECRET_NAME:-youtube-api-key}"
API_KEY_NAME="${SERVICE_NAME}-key"

RUNNER_SA_NAME="${SERVICE_NAME}-run"
SCHEDULER_SA_NAME="${SERVICE_NAME}-sched"
RUNNER_SA="${RUNNER_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
SCHEDULER_SA="${SCHEDULER_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

export CLOUDSDK_CORE_PROJECT="$PROJECT_ID"
export CLOUDSDK_CORE_DISABLE_PROMPTS=1

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '\033[1;33m    WARNING: %s\033[0m\n' "$*" >&2; }

# retry <attempts> <command...>  (IAM changes on new service accounts can take a minute to propagate)
retry() {
  local attempts="$1"; shift
  local n=1
  until "$@"; do
    if (( n >= attempts )); then return 1; fi
    sleep $(( n * 10 )); n=$(( n + 1 ))
  done
}

service_url() {
  gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format='value(status.url)' 2>/dev/null || true
}
