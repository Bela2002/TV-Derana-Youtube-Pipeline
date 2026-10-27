import dataclasses
from datetime import timedelta

from pipeline.config import load_settings
from pipeline.run import dry_run, run_pipeline
from pipeline.youtube_client import YouTubeClient

from .fakes import FakeWarehouse, FakeYouTube, now_utc


def make_settings(**overrides):
    base = load_settings()
    return dataclasses.replace(
        base, youtube_api_key="test-key", channel_id=None, channel_handle="@tvderanaofficial",
        gcp_project="proj", bq_dataset="ds", lookback_days=10,
        shorts_detection=("playlist", "duration"), **overrides,
    )


def test_full_run_with_fakes():
    fake = FakeYouTube(now_utc())
    yt = YouTubeClient("test-key", session=fake)
    wh = FakeWarehouse()
    summary = run_pipeline(make_settings(), yt=yt, warehouse=wh)

    assert summary["status"] == "success"
    # 10-day lookback with an upload every 6 hours -> 40 videos
    assert summary["videos_tracked"] == 40
    assert summary["new_videos"] == 40
    assert summary["playlist_scan"] == "2/3 playlists read in full"
    videos = wh.tables["videos"]
    assert {v["video_format"] for v in videos} == {"Short", "Long-form"}
    shorts = [v for v in videos if v["video_format"] == "Short"]
    assert all(v["format_method"] == "playlist" for v in shorts)
    assert len(wh.tables["video_snapshots"]) == 40
    assert wh.tables["channel_snapshots"][0]["subscriber_count"] == 6570000
    links = wh.tables["video_playlists"]
    assert links and all(link["video_id"].startswith("vid") for link in links)
    assert wh.tables["pipeline_runs"][-1]["status"] == "success"
    # empty playlist must not be requested
    assert not any(c[0] == "playlistItems" and c[1]["playlistId"] == "PLempty" for c in fake.calls)
    # write order: rules first, snapshots after dimensions, run log last
    names = [op[1] if isinstance(op, tuple) else op for op in wh.ops]
    assert names.index("category_rules") < names.index("videos") < names.index("video_snapshots")
    assert names[-1] == "pipeline_runs"


def test_failed_run_is_logged():
    fake = FakeYouTube(now_utc())

    def broken(params):
        from .fakes import FakeResponse
        return FakeResponse(403, {"error": {"errors": [{"reason": "quotaExceeded"}], "message": "quota"}})

    fake._videos = broken
    wh = FakeWarehouse()
    try:
        run_pipeline(make_settings(), yt=YouTubeClient("test-key", session=fake), warehouse=wh)
    except Exception as exc:
        assert "quota" in str(exc)
    else:
        raise AssertionError("expected failure")
    assert wh.tables["pipeline_runs"][-1]["status"] == "quota_exceeded"
    assert "video_snapshots" not in wh.tables  # nothing partial was written


def test_dry_run():
    fake = FakeYouTube(now_utc())
    result = dry_run(make_settings(), yt=YouTubeClient("test-key", session=fake))
    assert result["videos_tracked"] == 40
    assert result["uploaded_last_24h"] == 4
    assert "test-key" not in str(result)


def test_unchanged_playlists_are_skipped():
    now = now_utc()
    fake = FakeYouTube(now)
    wh = FakeWarehouse()
    # PLnews already scanned yesterday with the same item count -> skipped; PLdream changed -> read
    wh.state = {"PLnews": (60, now - timedelta(days=1)), "PLdream": (29, now - timedelta(days=1))}
    summary = run_pipeline(make_settings(), yt=YouTubeClient("test-key", session=fake), warehouse=wh)
    read = {c[1]["playlistId"] for c in fake.calls if c[0] == "playlistItems"}
    assert "PLdream" in read and "PLnews" not in read
    assert summary["playlist_scan"].startswith("1/3")
    rows = {r["playlist_id"]: r for r in wh.tables["playlists"]}
    assert rows["PLnews"]["last_scanned_at"] is not None  # previous scan time kept


def test_stale_playlist_is_rescanned():
    now = now_utc()
    fake = FakeYouTube(now)
    wh = FakeWarehouse()
    wh.state = {"PLnews": (60, now - timedelta(days=30)), "PLdream": (30, now - timedelta(days=1))}
    run_pipeline(make_settings(), yt=YouTubeClient("test-key", session=fake), warehouse=wh)
    read = {c[1]["playlistId"] for c in fake.calls if c[0] == "playlistItems"}
    assert "PLnews" in read and "PLdream" not in read


def test_other_failure_is_logged_as_failed():
    fake = FakeYouTube(now_utc())

    def broken(params):
        from .fakes import FakeResponse
        return FakeResponse(400, {"error": {"errors": [{"reason": "badRequest"}], "message": "bad"}})

    fake._videos = broken
    wh = FakeWarehouse()
    try:
        run_pipeline(make_settings(), yt=YouTubeClient("test-key", session=fake), warehouse=wh)
    except Exception:
        pass
    assert wh.tables["pipeline_runs"][-1]["status"] == "failed"
