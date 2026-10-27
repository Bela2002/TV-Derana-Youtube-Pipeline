"""Print a Looker Studio link that creates a new report already connected to BigQuery.

    python scripts/looker_link.py

Reads PROJECT_ID and BQ_DATASET from .env. Open the printed link while signed in with a Google
account that can read the dataset, then follow docs/DASHBOARD.md.
"""

import os
import sys
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pipeline.config  # noqa: E402,F401  (loads .env)

project = os.environ.get("PROJECT_ID") or os.environ.get("GCP_PROJECT_ID")
dataset = os.environ.get("BQ_DATASET", "youtube_derana")
if not project or project == "your-gcp-project-id":
    sys.exit("Set PROJECT_ID in .env first.")

params = {
    "r.reportName": "TV Derana YouTube Performance",
    "ds.ds0.connector": "bigQuery",
    "ds.ds0.type": "TABLE",
    "ds.ds0.projectId": project,
    "ds.ds0.datasetId": dataset,
    "ds.ds0.tableId": "v_window_videos",
    "ds.ds0.datasourceName": "v_window_videos",
}
print("Create the report (first data source = v_window_videos):")
print("https://lookerstudio.google.com/reporting/create?" + urlencode(params))
print("\nThen add the other views with Add data > BigQuery > {} > {}:".format(project, dataset))
for view in ("v_channel_daily", "v_weekly_summary", "v_rolling_comparison", "v_videos_latest",
             "v_window_summary", "v_breakdown_daily", "v_time_slots", "v_anomalies",
             "v_data_freshness", "v_report_daily"):
    print("  -", view)
