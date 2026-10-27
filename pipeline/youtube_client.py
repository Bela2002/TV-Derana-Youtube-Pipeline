"""Thin YouTube Data API v3 client using an API key (public data only)."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Iterator

import requests

from .transform import parse_rfc3339

API_BASE = "https://www.googleapis.com/youtube/v3"
log = logging.getLogger(__name__)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
RETRYABLE_REASONS = {"rateLimitExceeded", "userRateLimitExceeded", "backendError", "internalError"}
QUOTA_REASONS = {"quotaExceeded", "dailyLimitExceeded"}


class YouTubeApiError(RuntimeError):
    pass


class QuotaExceededError(YouTubeApiError):
    pass


class NotFoundError(YouTubeApiError):
    pass


def _error_details(resp: requests.Response) -> tuple[str, str]:
    try:
        err = resp.json().get("error", {})
        reason = (err.get("errors") or [{}])[0].get("reason", "") or err.get("status", "")
        return reason, err.get("message", "")
    except ValueError:
        return "", resp.text[:200]


class YouTubeClient:
    def __init__(self, api_key: str, session: requests.Session | None = None, max_retries: int = 4):
        self.api_key = api_key
        self.session = session or requests.Session()
        self.max_retries = max_retries
        self.units_used = 0

    # ------------------------------------------------------------------ core
    def _get(self, endpoint: str, params: dict, cost: int = 1) -> dict:
        query = {**params, "key": self.api_key}
        for attempt in range(self.max_retries + 1):
            try:
                resp = self.session.get(f"{API_BASE}/{endpoint}", params=query, timeout=30)
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise YouTubeApiError(f"{endpoint}: network error: {exc.__class__.__name__}") from None
                time.sleep(2**attempt)
                continue

            if resp.status_code == 200:
                self.units_used += cost
                return resp.json()

            reason, message = _error_details(resp)
            if resp.status_code == 403 and reason in QUOTA_REASONS:
                raise QuotaExceededError(f"{endpoint}: YouTube API quota exceeded ({message})")
            if resp.status_code == 404:
                raise NotFoundError(f"{endpoint}: not found ({reason})")
            if (resp.status_code in RETRYABLE_STATUS or reason in RETRYABLE_REASONS) and attempt < self.max_retries:
                wait = 2**attempt
                log.warning("%s returned %s (%s); retrying in %ss", endpoint, resp.status_code, reason, wait)
                time.sleep(wait)
                continue
            # Never include the request URL in errors: it contains the API key.
            raise YouTubeApiError(f"{endpoint}: HTTP {resp.status_code} {reason}: {message}")
        raise YouTubeApiError(f"{endpoint}: retries exhausted")  # pragma: no cover

    # -------------------------------------------------------------- channels
    def get_channel(self, channel_id: str | None = None, handle: str | None = None) -> dict:
        params = {"part": "snippet,statistics,contentDetails"}
        if channel_id:
            params["id"] = channel_id
        elif handle:
            params["forHandle"] = handle if handle.startswith("@") else f"@{handle}"
        else:
            raise ValueError("channel_id or handle is required")
        data = self._get("channels", params)
        items = data.get("items") or []
        if not items:
            raise YouTubeApiError(f"Channel not found for {channel_id or handle}")
        return items[0]

    # ------------------------------------------------------------- playlists
    def list_playlists(self, channel_id: str) -> list[dict]:
        playlists: list[dict] = []
        page_token = None
        while True:
            params = {"part": "snippet,contentDetails", "channelId": channel_id, "maxResults": 50}
            if page_token:
                params["pageToken"] = page_token
            data = self._get("playlists", params)
            playlists.extend(data.get("items") or [])
            page_token = data.get("nextPageToken")
            if not page_token:
                return playlists

    def iter_playlist_items(self, playlist_id: str, max_pages: int | None = None) -> Iterator[list[dict]]:
        """Yield playlist items one page (up to 50 items) at a time."""
        page_token = None
        pages = 0
        while True:
            params = {"part": "snippet,contentDetails", "playlistId": playlist_id, "maxResults": 50}
            if page_token:
                params["pageToken"] = page_token
            data = self._get("playlistItems", params)
            pages += 1
            yield data.get("items") or []
            page_token = data.get("nextPageToken")
            if not page_token or (max_pages is not None and pages >= max_pages):
                return

    def recent_video_ids(self, playlist_id: str, cutoff: datetime, hard_page_limit: int = 400) -> list[str]:
        """Video IDs from a newest-first playlist (e.g. the uploads playlist) published on/after cutoff.

        Stops after the first page in which every item is older than the cutoff.
        """
        ids: list[str] = []
        seen: set[str] = set()
        for page in self.iter_playlist_items(playlist_id, max_pages=hard_page_limit):
            page_has_recent = False
            for item in page:
                details = item.get("contentDetails") or {}
                vid = details.get("videoId")
                published = parse_rfc3339(details.get("videoPublishedAt"))
                if not vid or published is None:
                    continue  # private / deleted entries carry no publish date
                if published >= cutoff:
                    page_has_recent = True
                    if vid not in seen:
                        seen.add(vid)
                        ids.append(vid)
            if not page_has_recent:
                break
        return ids

    # ---------------------------------------------------------------- videos
    def get_videos(self, video_ids: list[str]) -> list[dict]:
        videos: list[dict] = []
        for start in range(0, len(video_ids), 50):
            batch = video_ids[start : start + 50]
            data = self._get(
                "videos",
                {"part": "snippet,contentDetails,statistics", "id": ",".join(batch), "maxResults": 50},
            )
            videos.extend(data.get("items") or [])
        return videos
