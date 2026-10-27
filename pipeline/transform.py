"""Pure functions that turn YouTube API resources into warehouse rows."""

from __future__ import annotations

import re
from datetime import datetime, timezone

_DURATION_RE = re.compile(
    r"^P(?:(?P<weeks>\d+)W)?(?:(?P<days>\d+)D)?"
    r"(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+(?:\.\d+)?)S)?)?$"
)


def parse_rfc3339(value: str | None) -> datetime | None:
    """Parse timestamps such as '2026-10-26T13:30:01Z' into aware UTC datetimes."""
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_iso8601_duration(value: str | None) -> int | None:
    """'PT1H2M3S' -> 3723 seconds. Returns None for missing or malformed values."""
    if not value:
        return None
    match = _DURATION_RE.match(value.strip())
    if not match:
        return None
    parts = {k: float(v) if v else 0.0 for k, v in match.groupdict().items()}
    total = (
        parts["weeks"] * 7 * 86400
        + parts["days"] * 86400
        + parts["hours"] * 3600
        + parts["minutes"] * 60
        + parts["seconds"]
    )
    return int(round(total))


def to_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def ts(value: datetime | None) -> str | None:
    """Datetime -> BigQuery-friendly ISO string (UTC)."""
    if value is None:
        return None
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# --------------------------------------------------------------------- rows
def channel_row(channel: dict, captured_at: datetime) -> dict:
    snippet = channel.get("snippet") or {}
    related = (channel.get("contentDetails") or {}).get("relatedPlaylists") or {}
    return {
        "channel_id": channel.get("id"),
        "channel_title": snippet.get("title"),
        "custom_url": snippet.get("customUrl"),
        "country": snippet.get("country"),
        "uploads_playlist_id": related.get("uploads"),
        "channel_created_at": ts(parse_rfc3339(snippet.get("publishedAt"))),
        "updated_at": ts(captured_at),
    }


def channel_snapshot_row(channel: dict, captured_at: datetime) -> dict:
    stats = channel.get("statistics") or {}
    snippet = channel.get("snippet") or {}
    return {
        "capture_date": captured_at.date().isoformat(),
        "capture_ts": ts(captured_at),
        "channel_id": channel.get("id"),
        "channel_title": snippet.get("title"),
        "subscriber_count": to_int(stats.get("subscriberCount")),
        "hidden_subscriber_count": bool(stats.get("hiddenSubscriberCount", False)),
        "view_count": to_int(stats.get("viewCount")),
        "video_count": to_int(stats.get("videoCount")),
    }


def video_row(video: dict, captured_at: datetime, is_short: bool | None, method: str) -> dict:
    snippet = video.get("snippet") or {}
    details = video.get("contentDetails") or {}
    live = snippet.get("liveBroadcastContent") or "none"
    duration_seconds = parse_iso8601_duration(details.get("duration"))
    if live in ("live", "upcoming"):
        video_format = "Live / Upcoming"
    elif is_short is None:
        video_format = "Unknown"
    else:
        video_format = "Short" if is_short else "Long-form"
    return {
        "video_id": video.get("id"),
        "channel_id": snippet.get("channelId"),
        "channel_title": snippet.get("channelTitle"),
        "title": snippet.get("title"),
        "published_at": ts(parse_rfc3339(snippet.get("publishedAt"))),
        "duration_iso": details.get("duration"),
        "duration_seconds": duration_seconds,
        "definition": details.get("definition"),
        "youtube_category_id": snippet.get("categoryId"),
        "default_audio_language": snippet.get("defaultAudioLanguage"),
        "live_broadcast_content": live,
        "is_short": is_short,
        "format_method": method,
        "video_format": video_format,
        "tags": "|".join(snippet.get("tags") or [])[:2000] or None,
        "first_seen_ts": ts(captured_at),
        "last_seen_ts": ts(captured_at),
    }


def video_snapshot_row(video: dict, captured_at: datetime) -> dict:
    stats = video.get("statistics") or {}
    snippet = video.get("snippet") or {}
    return {
        "capture_date": captured_at.date().isoformat(),
        "capture_ts": ts(captured_at),
        "channel_id": snippet.get("channelId"),
        "video_id": video.get("id"),
        # likeCount / commentCount are absent when hidden or disabled -> NULL, not 0
        "view_count": to_int(stats.get("viewCount")),
        "like_count": to_int(stats.get("likeCount")),
        "comment_count": to_int(stats.get("commentCount")),
    }


def playlist_row(playlist: dict, captured_at: datetime, last_scanned_at: datetime | None = None) -> dict:
    snippet = playlist.get("snippet") or {}
    return {
        "playlist_id": playlist.get("id"),
        "channel_id": snippet.get("channelId"),
        "playlist_title": snippet.get("title"),
        "item_count": to_int((playlist.get("contentDetails") or {}).get("itemCount")),
        "playlist_created_at": ts(parse_rfc3339(snippet.get("publishedAt"))),
        "updated_at": ts(captured_at),
        "last_scanned_at": ts(last_scanned_at),
    }


def video_playlist_row(video_id: str, playlist_id: str, captured_at: datetime) -> dict:
    return {
        "video_id": video_id,
        "playlist_id": playlist_id,
        "first_seen_ts": ts(captured_at),
        "last_seen_ts": ts(captured_at),
    }
