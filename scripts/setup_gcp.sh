#!/usr/bin/env bash
# One-time setup of the whole pipeline on Google Cloud. Safe to run again (idempotent).
#
#   APIs -> service accounts -> YouTube API key in Secret Manager -> BigQuery dataset
#   -> Cloud Run service (built from source, no Dockerfile) -> Cloud Scheduler daily job -> first run
#
# Usage:  bash scripts/setup_gcp.sh
source "$(dirname "$0")/_common.sh"

step "Project: $PROJECT_ID"
gcloud config set project "$PROJECT_ID" >/dev/null
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
BILLING="$(gcloud billing projects describe "$PROJECT_ID" --format='value(billingEnabled)' 2>/dev/null || echo unknown)"
if [[ "$BILLING" == "False" ]]; then
  echo "ERROR: billing is not enabled on $PROJECT_ID. Cloud Run and Cloud Scheduler need a billing" >&2
  echo "       account linked (usage stays inside the free tier). Link one, then re-run." >&2
  exit 1
fi

step "Enabling APIs (takes 1-2 minutes the first time)"
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  cloudscheduler.googleapis.com \
  bigquery.googleapis.com \
  secretmanager.googleapis.com \
  youtube.googleapis.com \
  apikeys.googleapis.com \
  iam.googleapis.com

step "Service accounts"
for pair in "$RUNNER_SA_NAME:YouTube pipeline (Cloud Run runtime)" "$SCHEDULER_SA_NAME:YouTube pipeline (Cloud Scheduler caller)"; do
  name="${pair%%:*}"; display="${pair#*:}"
  if gcloud iam service-accounts describe "${name}@${PROJECT_ID}.iam.gserviceaccount.com" >/dev/null 2>&1; then
    info "$name exists"
  else
    gcloud iam service-accounts create "$name" --display-name="$display" >/dev/null
    info "created $name"
  fi
done

step "IAM roles"
# Job User lets the pipeline run load/query jobs but grants no access to any data.
# Data access is granted on the pipeline's own dataset only (see the BigQuery step below).
retry 6 gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${RUNNER_SA}" --role=roles/bigquery.jobUser --condition=None >/dev/null
info "$RUNNER_SA_NAME -> roles/bigquery.jobUser (project: run jobs only, no data access)"
# Remove project-wide data access in case an older version of this script granted it.
if gcloud projects get-iam-policy "$PROJECT_ID" --flatten='bindings[].members' \
     --filter="bindings.role=roles/bigquery.dataEditor AND bindings.members=serviceAccount:${RUNNER_SA}" \
     --format='value(bindings.role)' 2>/dev/null | grep -q dataEditor; then
  gcloud projects remove-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${RUNNER_SA}" --role=roles/bigquery.dataEditor --all >/dev/null
  info "removed old project-wide roles/bigquery.dataEditor from $RUNNER_SA_NAME"
fi
# Source deploys build with the Compute Engine default service account, which needs Cloud Run Builder.
BUILD_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
if gcloud iam service-accounts describe "$BUILD_SA" >/dev/null 2>&1; then
  retry 3 gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${BUILD_SA}" --role=roles/run.builder --condition=None >/dev/null \
    && info "build account -> roles/run.builder" \
    || warn "could not grant roles/run.builder to $BUILD_SA (deploy may fail; grant it in IAM)"
else
  warn "default compute service account not found; if the build fails, see docs/SETUP_GCP.md > Troubleshooting"
fi

step "YouTube API key (Secret Manager: $SECRET_NAME)"
if ! gcloud secrets describe "$SECRET_NAME" >/dev/null 2>&1; then
  KEY="${YOUTUBE_API_KEY:-}"
  if [[ -z "$KEY" ]]; then
    info "no YOUTUBE_API_KEY in .env - creating a key restricted to YouTube Data API v3"
    gcloud services api-keys create --display-name="$API_KEY_NAME" \
      --api-target=service=youtube.googleapis.com >/dev/null
    KEY_RESOURCE="$(gcloud services api-keys list --filter="displayName=${API_KEY_NAME}" --format='value(name)' --limit=1)"
    KEY="$(gcloud services api-keys get-key-string "$KEY_RESOURCE" --format='value(keyString)')"
  fi
  printf '%s' "$KEY" | gcloud secrets create "$SECRET_NAME" --replication-policy=automatic --data-file=- >/dev/null
  info "secret created"
elif [[ -n "${YOUTUBE_API_KEY:-}" ]]; then
  CURRENT="$(gcloud secrets versions access latest --secret="$SECRET_NAME" 2>/dev/null || true)"
  if [[ "$CURRENT" != "$YOUTUBE_API_KEY" ]]; then
    printf '%s' "$YOUTUBE_API_KEY" | gcloud secrets versions add "$SECRET_NAME" --data-file=- >/dev/null
    info "secret updated with the key from .env"
  else
    info "secret already up to date"
  fi
else
  info "secret exists"
fi
retry 6 gcloud secrets add-iam-policy-binding "$SECRET_NAME" \
  --member="serviceAccount:${RUNNER_SA}" --role=roles/secretmanager.secretAccessor >/dev/null
info "$RUNNER_SA_NAME can read the secret"

step "BigQuery dataset ${PROJECT_ID}:${BQ_DATASET} (${BQ_LOCATION})"
if bq --project_id="$PROJECT_ID" show --dataset "${PROJECT_ID}:${BQ_DATASET}" >/dev/null 2>&1; then
  info "dataset exists"
else
  bq --project_id="$PROJECT_ID" --location="$BQ_LOCATION" mk --dataset \
    --description="Daily YouTube performance data" "${PROJECT_ID}:${BQ_DATASET}" >/dev/null
  info "dataset created (tables and views are created by the first pipeline run)"
fi

step "Dataset access: $RUNNER_SA_NAME can edit ${BQ_DATASET} only"
grant_dataset_writer() {
  local file; file="$(mktemp)"
  bq --project_id="$PROJECT_ID" show --format=prettyjson "${PROJECT_ID}:${BQ_DATASET}" > "$file" || { rm -f "$file"; return 1; }
  local result
  result="$(python3 - "$file" "$RUNNER_SA" <<'PY'
import json, sys
path, email = sys.argv[1], sys.argv[2]
ds = json.load(open(path))
access = ds.get("access", [])
writer_roles = {"WRITER", "roles/bigquery.dataEditor"}
if any(a.get("userByEmail") == email and a.get("role") in writer_roles for a in access):
    print("present")
else:
    access = [a for a in access if a.get("userByEmail") != email]
    access.append({"role": "WRITER", "userByEmail": email})
    ds["access"] = access
    json.dump(ds, open(path, "w"))
    print("added")
PY
)" || { rm -f "$file"; return 1; }
  if [[ "$result" == "added" ]]; then
    bq --project_id="$PROJECT_ID" update --source "$file" "${PROJECT_ID}:${BQ_DATASET}" >/dev/null \
      || { rm -f "$file"; return 1; }
    info "granted dataset WRITER (BigQuery Data Editor on this dataset)"
  else
    info "already has dataset WRITER"
  fi
  rm -f "$file"
}
retry 6 grant_dataset_writer

bash "$REPO_ROOT/scripts/deploy.sh"

step "First run (fills BigQuery now instead of waiting for the schedule)"
bash "$REPO_ROOT/scripts/run_now.sh" || warn "first run failed - see the message above and docs/SETUP_GCP.md > Troubleshooting"

step "Done"
info "Cloud Run service : $SERVICE_NAME ($REGION)"
info "Daily schedule    : '$SCHEDULE' ($SCHEDULE_TIMEZONE) via Cloud Scheduler job $SCHEDULER_JOB"
info "BigQuery dataset  : ${PROJECT_ID}.${BQ_DATASET}"
info "Next: build the dashboard - docs/DASHBOARD.md (python3 scripts/looker_link.py prints a ready link)"
