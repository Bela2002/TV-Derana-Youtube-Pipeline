#!/usr/bin/env bash
# Build the code with Cloud Build (Python buildpack, no Dockerfile), deploy it to Cloud Run
# and create/update the Cloud Scheduler job. Run after any code or config change.
#
# Usage:  bash scripts/deploy.sh
source "$(dirname "$0")/_common.sh"

step "Deploying Cloud Run service $SERVICE_NAME (build takes 2-4 minutes)"
ENV_FILE="$(mktemp)"
trap 'rm -f "$ENV_FILE"' EXIT
cat > "$ENV_FILE" <<YAML
GCP_PROJECT_ID: "${PROJECT_ID}"
BQ_DATASET: "${BQ_DATASET}"
BQ_LOCATION: "${BQ_LOCATION}"
CHANNEL_HANDLE: "${CHANNEL_HANDLE}"
CHANNEL_ID: "${CHANNEL_ID}"
LOOKBACK_DAYS: "${LOOKBACK_DAYS}"
SHORTS_DETECTION: "${SHORTS_DETECTION}"
SHORTS_MAX_SECONDS: "${SHORTS_MAX_SECONDS}"
REPORT_TIMEZONE: "${REPORT_TIMEZONE}"
PLAYLIST_PAGE_BUDGET: "${PLAYLIST_PAGE_BUDGET}"
PLAYLIST_MAX_PAGES: "${PLAYLIST_MAX_PAGES}"
PLAYLIST_RESCAN_DAYS: "${PLAYLIST_RESCAN_DAYS}"
YAML

gcloud run deploy "$SERVICE_NAME" \
  --source . \
  --region "$REGION" \
  --service-account "$RUNNER_SA" \
  --no-allow-unauthenticated \
  --env-vars-file "$ENV_FILE" \
  --set-secrets "YOUTUBE_API_KEY=${SECRET_NAME}:latest" \
  --memory 512Mi \
  --cpu 1 \
  --concurrency 1 \
  --min-instances 0 \
  --max-instances 1 \
  --timeout 1800 \
  --quiet

URL="$(service_url)"
info "service URL: $URL"

step "Allowing the scheduler account to call the service"
retry 6 gcloud run services add-iam-policy-binding "$SERVICE_NAME" --region "$REGION" \
  --member="serviceAccount:${SCHEDULER_SA}" --role=roles/run.invoker >/dev/null
info "$SCHEDULER_SA_NAME -> roles/run.invoker"

step "Cloud Scheduler job $SCHEDULER_JOB ('$SCHEDULE', $SCHEDULE_TIMEZONE)"
if gcloud scheduler jobs describe "$SCHEDULER_JOB" --location "$REGION" >/dev/null 2>&1; then
  ACTION=update
else
  ACTION=create
fi
gcloud scheduler jobs "$ACTION" http "$SCHEDULER_JOB" \
  --location "$REGION" \
  --schedule "$SCHEDULE" \
  --time-zone "$SCHEDULE_TIMEZONE" \
  --uri "${URL}/run" \
  --http-method POST \
  --oidc-service-account-email "$SCHEDULER_SA" \
  --oidc-token-audience "$URL" \
  --attempt-deadline 1800s \
  --max-retry-attempts 2 \
  --min-backoff 600s \
  --description "Daily YouTube performance collection" >/dev/null
info "scheduler job ${ACTION}d"
