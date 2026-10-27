"""Cloud Run entry point. Cloud Scheduler calls POST /run once a day."""

import logging
import os

from flask import Flask, jsonify

from pipeline.run import run_pipeline
from pipeline.youtube_client import QuotaExceededError

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
app = Flask(__name__)


@app.get("/")
def health():
    return jsonify(status="ok", service="youtube-performance-pipeline")


@app.post("/run")
def run():
    try:
        return jsonify(run_pipeline()), 200
    except QuotaExceededError as exc:
        # Retrying cannot help until the daily YouTube quota resets (midnight Pacific time), so answer
        # 200 to stop Cloud Scheduler retries. The failure is still logged at ERROR level (for alerts)
        # and recorded in the pipeline_runs table with status "quota_exceeded".
        logging.error("Pipeline stopped: YouTube API quota exceeded: %s", exc)
        return jsonify(status="quota_exceeded", error=str(exc), retry="next scheduled run"), 200
    except Exception as exc:  # noqa: BLE001 - report every failure to the scheduler
        logging.exception("Pipeline run failed")
        return jsonify(status="failed", error=str(exc)), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
