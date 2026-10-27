from datetime import datetime, timezone

import pytest

from pipeline import transform


@pytest.mark.parametrize(
    "value, expected",
    [
        ("PT1H2M3S", 3723),
        ("PT45S", 45),
        ("PT3M", 180),
        ("P0D", 0),
        ("P1DT2H", 93600),
        ("PT1M30.5S", 90),
        ("", None),
        (None, None),
        ("garbage", None),
    ],
)
def test_parse_duration(value, expected):
    assert transform.parse_iso8601_duration(value) == expected


def test_parse_rfc3339_utc():
    parsed = transform.parse_rfc3339("2026-10-26T13:30:01Z")
    assert parsed == datetime(2026, 10, 26, 13, 30, 1, tzinfo=timezone.utc)
    assert transform.parse_rfc3339("bad") is None


def test_hidden_counts_become_null():
    captured = datetime(2026, 10, 27, 18, 35, tzinfo=timezone.utc)
    video = {"id": "abc", "snippet": {"channelId": "UC1"}, "statistics": {"viewCount": "10"}}
    row = transform.video_snapshot_row(video, captured)
    assert row["view_count"] == 10
    assert row["like_count"] is None and row["comment_count"] is None
    assert row["capture_date"] == "2026-10-27"


def test_video_row_formats():
    captured = datetime(2026, 10, 27, tzinfo=timezone.utc)
    base = {
        "id": "v",
        "snippet": {"title": "t", "liveBroadcastContent": "none"},
        "contentDetails": {"duration": "PT30S"},
    }
    assert transform.video_row(base, captured, True, "playlist")["video_format"] == "Short"
    assert transform.video_row(base, captured, False, "url")["video_format"] == "Long-form"
    live = {**base, "snippet": {"liveBroadcastContent": "upcoming"}}
    assert transform.video_row(live, captured, False, "live")["video_format"] == "Live / Upcoming"
