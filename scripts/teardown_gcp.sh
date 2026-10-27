#!/usr/bin/env bash
# Remove everything setup_gcp.sh created. The BigQuery dataset is kept unless --delete-data is given.
#
# Usage:  bash scripts/teardown_gcp.sh [--delete-data]
source "$(dirname "$0")/_common.sh"
DELETE_DATA="${1:-}"

step "Deleting Cloud Scheduler job";  gcloud scheduler jobs delete "$SCHEDULER_JOB" --location "$REGION" --quiet 2>/dev/null || info "not found"
step "Deleting Cloud Run service";    gcloud run services delete "$SERVICE_NAME" --region "$REGION" --quiet 2>/dev/null || info "not found"
step "Deleting secret";               gcloud secrets delete "$SECRET_NAME" --quiet 2>/dev/null || info "not found"
step "Deleting API key"
KEY_RESOURCE="$(gcloud services api-keys list --filter="displayName=${API_KEY_NAME}" --format='value(name)' --limit=1 2>/dev/null || true)"
if [[ -n "$KEY_RESOURCE" ]]; then gcloud services api-keys delete "$KEY_RESOURCE" --quiet >/dev/null; else info "not found"; fi
step "Deleting service accounts"
for sa in "$RUNNER_SA" "$SCHEDULER_SA"; do
  gcloud iam service-accounts delete "$sa" --quiet 2>/dev/null || info "$sa not found"
done
if [[ "$DELETE_DATA" == "--delete-data" ]]; then
  step "Deleting BigQuery dataset ${BQ_DATASET} and all its data"
  bq --project_id="$PROJECT_ID" rm -r -f --dataset "${PROJECT_ID}:${BQ_DATASET}" || true
else
  info "BigQuery dataset ${BQ_DATASET} kept (add --delete-data to remove it)"
fi
info "Container images remain in Artifact Registry repository 'cloud-run-source-deploy' ($REGION); delete it in the console if not needed."
