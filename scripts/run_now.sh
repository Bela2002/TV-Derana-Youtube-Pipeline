#!/usr/bin/env bash
# Run the pipeline immediately (same request Cloud Scheduler sends) and print the result.
#
# Usage:  bash scripts/run_now.sh
source "$(dirname "$0")/_common.sh"

URL="$(service_url)"
if [[ -z "$URL" ]]; then
  echo "ERROR: Cloud Run service $SERVICE_NAME not found in $REGION. Run scripts/setup_gcp.sh first." >&2
  exit 1
fi
step "Calling ${URL}/run (usually 1-5 minutes)"
TOKEN="$(gcloud auth print-identity-token)"
HTTP_CODE="$(curl -sS -o /tmp/yt_pipeline_run.json -w '%{http_code}' --max-time 1800 \
  -X POST -H "Authorization: Bearer ${TOKEN}" "${URL}/run")"
cat /tmp/yt_pipeline_run.json; echo
STATUS="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("status",""))' /tmp/yt_pipeline_run.json 2>/dev/null || true)"
if [[ "$STATUS" == "quota_exceeded" ]]; then
  echo "YouTube API daily quota is used up. It resets at midnight Pacific time; the next scheduled run will collect." >&2
  exit 1
fi
if [[ "$HTTP_CODE" != "200" ]]; then
  echo "Run failed with HTTP $HTTP_CODE. Logs:" >&2
  echo "  gcloud run services logs read $SERVICE_NAME --region $REGION --limit 50" >&2
  exit 1
fi
