"""Pipeline orchestration and command line entry point.

    python -m pipeline.run              # full run: YouTube API -> BigQuery
    python -m pipeline.run --dry-run    # call the YouTube API only, print what would be loaded
    python -m pipeline.run --init-only  # create dataset, tables and views, no API calls
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from . import shorts, transform
from .categorize import load_rules
from .config import Settings, load_settings
from .youtube_client import NotFoundError, QuotaExceededError, YouTubeClient

log = logging.getLogger("pipeline")


@dataclass
class Collected:
    captured_at: datetime
    channel: dict
    videos: list[dict] = field(default_factory=list)
    playlists: list[dict] = field(default_factory=list)
    links: list[tuple[str, str]] = field(default_factory=list)
    shorts_ids: set[str] | None = None
    playlist_scan: str = ""
    scanned_at: dict[str, datetime | None] = field(default_factory=dict)


# ------------------------------------------------------------------ extract
def collect(
    settings: Settings,
    yt: YouTubeClient,
    captured_at: datetime,
    playlist_state: dict[str, tuple[int | None, datetime | None]] | None = None,
) -> Collected:
    playlist_state = playlist_state or {}
    channel = yt.get_channel(settings.channel_id, settings.channel_handle)
    channel_id = channel["id"]
    uploads = ((channel.get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads")
    uploads = uploads or "UU" + channel_id[2:]
    cutoff = captured_at - timedelta(days=settings.lookback_days)
    log.info("Channel %s (%s); tracking uploads since %s", channel["snippet"]["title"], channel_id, cutoff.date())

    video_ids = yt.recent_video_ids(uploads, cutoff)
    log.info("Found %d uploads in the last %d days", len(video_ids), settings.lookback_days)

    data = Collected(captured_at=captured_at, channel=channel)
    if "playlist" in settings.shorts_detection:
        shorts_pl = shorts.shorts_playlist_id(channel_id)
        try:
            data.shorts_ids = set(yt.recent_video_ids(shorts_pl, cutoff)) if shorts_pl else None
        except NotFoundError:
            log.warning("Shorts playlist not available; falling back to other Shorts detection methods")

    data.videos = yt.get_videos(video_ids)

    # Playlists and video -> playlist links (program mapping).
    # A playlist is re-read only when it is new, its item count changed, or its last full
    # scan is older than PLAYLIST_RESCAN_DAYS - this keeps the daily run fast and cheap.
    data.playlists = yt.list_playlists(channel_id)
    tracked = {v["id"] for v in data.videos}
    rescan_before = captured_at - timedelta(days=settings.playlist_rescan_days)
    to_scan = []
    for playlist in data.playlists:
        count = transform.to_int((playlist.get("contentDetails") or {}).get("itemCount")) or 0
        prev_count, prev_scanned = playlist_state.get(playlist["id"], (None, None))
        data.scanned_at[playlist["id"]] = prev_scanned
        if count == 0:
            continue
        if prev_count != count or prev_scanned is None or prev_scanned < rescan_before:
            to_scan.append((playlist, count))
    pages_needed = sum(max(1, math.ceil(count / 50)) for _, count in to_scan)
    full_scan = pages_needed <= settings.playlist_page_budget
    page_cap = None if full_scan else settings.playlist_max_pages
    data.playlist_scan = (
        f"{len(to_scan)}/{len(data.playlists)} playlists read "
        + ("in full" if full_scan else f"(first {page_cap} pages each, budget exceeded)")
    )
    log.info("Playlists: %s (~%d pages)", data.playlist_scan, pages_needed)
    for playlist, _ in to_scan:
        try:
            for page in yt.iter_playlist_items(playlist["id"], max_pages=page_cap):
                for item in page:
                    vid = (item.get("contentDetails") or {}).get("videoId")
                    if vid in tracked:
                        data.links.append((vid, playlist["id"]))
            if full_scan:
                data.scanned_at[playlist["id"]] = captured_at
        except NotFoundError:
            log.warning("Playlist %s disappeared during the scan; skipped", playlist["id"])
    return data


# ---------------------------------------------------------------- transform
def build_rows(settings: Settings, data: Collected, known: dict[str, tuple[bool | None, str]]) -> dict[str, list]:
    captured_at = data.captured_at
    session = None
    checks = {"count": 0}

    def url_checker(video_id: str):
        nonlocal session
        import requests

        session = session or requests.Session()
        checks["count"] += 1
        return shorts.check_shorts_url(video_id, session)

    videos, snapshots = [], []
    for video in data.videos:
        duration = transform.parse_iso8601_duration((video.get("contentDetails") or {}).get("duration"))
        live = (video.get("snippet") or {}).get("liveBroadcastContent") or "none"
        is_short, method = shorts.classify(
            video["id"], duration, live, settings.shorts_detection, settings.shorts_max_seconds,
            data.shorts_ids, known, url_checker,
        )
        videos.append(transform.video_row(video, captured_at, is_short, method))
        snapshots.append(transform.video_snapshot_row(video, captured_at))
    if checks["count"]:
        log.info("Checked %d videos via the Shorts URL", checks["count"])

    return {
        "channels": [transform.channel_row(data.channel, captured_at)],
        "channel_snapshots": [transform.channel_snapshot_row(data.channel, captured_at)],
        "videos": videos,
        "video_snapshots": snapshots,
        "playlists": [transform.playlist_row(p, captured_at, data.scanned_at.get(p["id"])) for p in data.playlists],
        "video_playlists": [transform.video_playlist_row(v, p, captured_at) for v, p in data.links],
    }


# --------------------------------------------------------------------- load
def view_params(settings: Settings, warehouse, default_category: str) -> dict[str, str]:
    return {
        "dataset_ref": warehouse.dataset_ref,
        "timezone": settings.report_timezone.replace("'", ""),
        "default_category": default_category.replace("'", "\\'"),
        "shorts_max_seconds": str(settings.shorts_max_seconds),
    }


def init_warehouse(settings: Settings, warehouse=None):
    from .warehouse import Warehouse

    settings.require_bigquery()
    warehouse = warehouse or Warehouse(settings.gcp_project, settings.bq_dataset, settings.bq_location)
    warehouse.ensure_dataset()
    warehouse.ensure_tables()
    rules, default_category = load_rules(settings.rules_path)
    warehouse.replace_table("category_rules", rules)
    views = warehouse.deploy_views(settings.sql_dir, view_params(settings, warehouse, default_category))
    return warehouse, views


def run_pipeline(settings: Settings | None = None, yt: YouTubeClient | None = None, warehouse=None) -> dict:
    settings = settings or load_settings()
    settings.require_youtube()
    started = time.time()
    captured_at = datetime.now(timezone.utc).replace(microsecond=0)
    run_id = uuid.uuid4().hex[:12]
    yt = yt or YouTubeClient(settings.youtube_api_key)

    warehouse, _ = init_warehouse(settings, warehouse)
    run_row = {
        "run_id": run_id,
        "started_at": transform.ts(captured_at),
        "capture_date": captured_at.date().isoformat(),
    }
    try:
        data = collect(settings, yt, captured_at, warehouse.playlist_state())
        known = warehouse.existing_videos([v["id"] for v in data.videos])
        rows = build_rows(settings, data, known)

        warehouse.upsert("channels", rows["channels"], keys=["channel_id"])
        warehouse.upsert("playlists", rows["playlists"], keys=["playlist_id"])
        warehouse.upsert("videos", rows["videos"], keys=["video_id"], keep_on_update=("first_seen_ts",))
        warehouse.upsert(
            "video_playlists", rows["video_playlists"], keys=["video_id", "playlist_id"],
            keep_on_update=("first_seen_ts",),
        )
        warehouse.replace_partition("channel_snapshots", captured_at.date(), rows["channel_snapshots"])
        warehouse.replace_partition("video_snapshots", captured_at.date(), rows["video_snapshots"])

        summary = {
            "status": "success",
            "run_id": run_id,
            "capture_ts_utc": transform.ts(captured_at),
            "channel": data.channel["snippet"]["title"],
            "channel_id": data.channel["id"],
            "videos_tracked": len(rows["videos"]),
            "new_videos": len([v for v in rows["videos"] if v["video_id"] not in known]),
            "playlists": len(rows["playlists"]),
            "playlist_links": len(rows["video_playlists"]),
            "playlist_scan": data.playlist_scan,
            "api_units_used": yt.units_used,
            "seconds": round(time.time() - started, 1),
        }
        run_row.update(
            status="success", channel_id=summary["channel_id"], videos_tracked=summary["videos_tracked"],
            new_videos=summary["new_videos"], playlists=summary["playlists"], api_units_used=yt.units_used,
            message=f"playlist scan: {data.playlist_scan}",
        )
        return summary
    except QuotaExceededError as exc:
        run_row.update(status="quota_exceeded", api_units_used=yt.units_used, message=str(exc)[:1000])
        raise
    except Exception as exc:
        run_row.update(status="failed", api_units_used=yt.units_used, message=str(exc)[:1000])
        raise
    finally:
        run_row["finished_at"] = transform.ts(datetime.now(timezone.utc))
        try:
            warehouse.append("pipeline_runs", [run_row])
        except Exception:  # logging the run must never hide the real error
            log.exception("Could not write pipeline_runs row")


def dry_run(settings: Settings | None = None, yt: YouTubeClient | None = None) -> dict:
    settings = settings or load_settings()
    settings.require_youtube()
    yt = yt or YouTubeClient(settings.youtube_api_key)
    captured_at = datetime.now(timezone.utc).replace(microsecond=0)
    data = collect(settings, yt, captured_at)
    rows = build_rows(settings, data, known={})
    formats: dict[str, int] = {}
    for v in rows["videos"]:
        formats[v["video_format"]] = formats.get(v["video_format"], 0) + 1
    last_24h = [
        v for v in rows["videos"]
        if v["published_at"] and transform.parse_rfc3339(v["published_at"]) >= captured_at - timedelta(hours=24)
    ]
    return {
        "status": "dry-run (nothing written)",
        "channel": data.channel["snippet"]["title"],
        "channel_id": data.channel["id"],
        "subscribers": rows["channel_snapshots"][0]["subscriber_count"],
        "videos_tracked": len(rows["videos"]),
        "uploaded_last_24h": len(last_24h),
        "formats": formats,
        "playlists": len(rows["playlists"]),
        "playlist_links": len(rows["video_playlists"]),
        "api_units_used": yt.units_used,
        "sample_video": rows["videos"][0] if rows["videos"] else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Daily YouTube performance pipeline")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="fetch from YouTube only; write nothing")
    group.add_argument("--init-only", action="store_true", help="create dataset, tables and views only")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    settings = load_settings()
    if args.init_only:
        _, views = init_warehouse(settings)
        result = {"status": "initialised", "dataset": f"{settings.gcp_project}.{settings.bq_dataset}", "views": views}
    elif args.dry_run:
        result = dry_run(settings)
    else:
        result = run_pipeline(settings)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
