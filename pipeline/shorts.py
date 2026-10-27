"""Shorts vs long-form classification.

YouTube Data API v3 has no "isShort" field, so three methods are combined (order set by
SHORTS_DETECTION):

* playlist - membership of the channel's auto-generated Shorts playlist (UUSH + channel suffix)
* url      - https://www.youtube.com/shorts/<id> answers 200 for a Short and redirects otherwise
* duration - anything up to SHORTS_MAX_SECONDS is treated as a Short (last-resort heuristic)

A video longer than SHORTS_MAX_SECONDS can never be a Short, so it is classified without any lookup.
"""

from __future__ import annotations

import logging
from typing import Callable

import requests

log = logging.getLogger(__name__)

Classification = tuple[bool | None, str]


def shorts_playlist_id(channel_id: str) -> str | None:
    if channel_id and channel_id.startswith("UC"):
        return "UUSH" + channel_id[2:]
    return None


def check_shorts_url(video_id: str, session: requests.Session | None = None) -> bool | None:
    """True = Short, False = regular video, None = could not tell."""
    http = session or requests
    try:
        resp = http.head(
            f"https://www.youtube.com/shorts/{video_id}",
            allow_redirects=False,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (compatible; yt-performance-pipeline)"},
        )
    except requests.RequestException:
        return None
    if resp.status_code == 200:
        return True
    if resp.status_code in (301, 302, 303, 307, 308):
        location = resp.headers.get("Location", "")
        if "consent." in location:
            return None
        if "/watch" in location:
            return False
    return None


def classify(
    video_id: str,
    duration_seconds: int | None,
    live_broadcast_content: str,
    methods: tuple[str, ...],
    max_seconds: int,
    shorts_ids: set[str] | None,
    cache: dict[str, Classification],
    url_checker: Callable[[str], bool | None],
) -> Classification:
    if live_broadcast_content in ("live", "upcoming"):
        return False, "live"
    if duration_seconds is not None and duration_seconds > max_seconds:
        return False, "duration"

    playlist_negative = False
    for method in methods:
        if method == "playlist" and shorts_ids is not None:
            if video_id in shorts_ids:
                return True, "playlist"
            playlist_negative = True
        elif method == "url":
            cached = cache.get(video_id)
            if cached and cached[1] == "url":
                return cached
            result = url_checker(video_id)
            if result is not None:
                return result, "url"
        elif method == "duration":
            if duration_seconds is None:
                return None, "unknown"
            return True, "duration"

    if playlist_negative:
        return False, "playlist"
    return None, "unknown"
