from pipeline.shorts import classify, shorts_playlist_id

METHODS = ("playlist", "url", "duration")


def no_url(_):
    return None


def test_playlist_id():
    assert shorts_playlist_id("UCabc") == "UUSHabc"
    assert shorts_playlist_id("bad") is None


def test_long_video_never_short():
    assert classify("v", 600, "none", METHODS, 180, set(), {}, no_url) == (False, "duration")


def test_playlist_member_is_short():
    assert classify("v", 50, "none", METHODS, 180, {"v"}, {}, no_url) == (True, "playlist")


def test_url_check_used_when_not_in_playlist():
    assert classify("v", 50, "none", METHODS, 180, set(), {}, lambda _: False) == (False, "url")


def test_url_cache_avoids_http():
    def boom(_):
        raise AssertionError("should use cache")

    assert classify("v", 50, "none", METHODS, 180, set(), {"v": (True, "url")}, boom) == (True, "url")


def test_duration_fallback():
    assert classify("v", 50, "none", METHODS, 180, None, {}, no_url) == (True, "duration")
    assert classify("v", 50, "none", ("playlist",), 180, set(), {}, no_url) == (False, "playlist")


def test_live():
    assert classify("v", 0, "live", METHODS, 180, None, {}, no_url) == (False, "live")
