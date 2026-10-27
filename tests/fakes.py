"""In-memory stand-ins for the YouTube API and BigQuery used by the tests."""

from datetime import datetime, timedelta, timezone

CHANNEL_ID = "UCtestchannel0000000000"


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class FakeYouTube:
    """Routes requests.Session.get calls to canned data."""

    def __init__(self, now: datetime, n_videos: int = 120):
        self.now = now
        self.calls = []
        self.videos = []
        for i in range(n_videos):
            published = now - timedelta(hours=6 * i + 1)
            short = i % 3 == 0
            self.videos.append({
                "id": f"vid{i:04d}",
                "snippet": {
                    "publishedAt": _iso(published),
                    "channelId": CHANNEL_ID,
                    "channelTitle": "TV Derana",
                    "title": ["Derana Dream Star S12 Ep %d" % i, "Ada Derana News %d" % i,
                              "Teledrama Episode %d" % i, "Cricket highlights %d" % i][i % 4],
                    "liveBroadcastContent": "none",
                    "categoryId": "24",
                },
                "contentDetails": {"duration": "PT45S" if short else "PT24M10S", "definition": "hd",
                                   "videoPublishedAt": _iso(published)},
                "statistics": {"viewCount": str(1000 * (n_videos - i)), "likeCount": str(10 * i),
                               "commentCount": str(i)},
            })
        self.playlists = [
            {"id": "PLnews", "snippet": {"title": "Ada Derana News", "channelId": CHANNEL_ID,
                                         "publishedAt": _iso(now)}, "contentDetails": {"itemCount": 60}},
            {"id": "PLdream", "snippet": {"title": "Derana Dream Star Season 12", "channelId": CHANNEL_ID,
                                          "publishedAt": _iso(now)}, "contentDetails": {"itemCount": 30}},
            {"id": "PLempty", "snippet": {"title": "Empty", "channelId": CHANNEL_ID,
                                          "publishedAt": _iso(now)}, "contentDetails": {"itemCount": 0}},
        ]
        self.playlist_members = {
            "PLnews": [v["id"] for v in self.videos if "News" in v["snippet"]["title"]],
            "PLdream": [v["id"] for v in self.videos if "Dream" in v["snippet"]["title"]],
        }

    # requests.Session API
    def get(self, url, params=None, timeout=None):
        endpoint = url.rsplit("/", 1)[-1]
        self.calls.append((endpoint, dict(params or {})))
        assert params.get("key") == "test-key"
        return getattr(self, "_" + endpoint)(params)

    def _page(self, items, params, size=50):
        start = int(params.get("pageToken") or 0)
        page = items[start:start + size]
        payload = {"items": page}
        if start + size < len(items):
            payload["nextPageToken"] = str(start + size)
        return FakeResponse(200, payload)

    def _channels(self, params):
        assert params.get("forHandle") == "@tvderanaofficial"
        return FakeResponse(200, {"items": [{
            "id": CHANNEL_ID,
            "snippet": {"title": "TV Derana", "customUrl": "@tvderanaofficial", "publishedAt": "2012-01-26T00:00:00Z"},
            "statistics": {"subscriberCount": "6570000", "viewCount": "6130000000", "videoCount": "51000",
                           "hiddenSubscriberCount": False},
            "contentDetails": {"relatedPlaylists": {"uploads": "UU" + CHANNEL_ID[2:]}},
        }]})

    def _playlistItems(self, params):
        pid = params["playlistId"]
        if pid.startswith("UUSH"):
            vids = [v for v in self.videos if v["contentDetails"]["duration"] == "PT45S"]
        elif pid.startswith("UU"):
            vids = self.videos
        else:
            ids = self.playlist_members.get(pid, [])
            vids = [v for v in self.videos if v["id"] in ids]
        items = [{"contentDetails": {"videoId": v["id"], "videoPublishedAt": v["snippet"]["publishedAt"]}}
                 for v in vids]
        return self._page(items, params)

    def _playlists(self, params):
        return self._page(self.playlists, params)

    def _videos(self, params):
        ids = params["id"].split(",")
        assert len(ids) <= 50
        return FakeResponse(200, {"items": [v for v in self.videos if v["id"] in ids]})


class FakeWarehouse:
    dataset_ref = "proj.ds"

    def __init__(self):
        self.ops = []
        self.tables = {}

    def ensure_dataset(self):
        self.ops.append("ensure_dataset")

    def ensure_tables(self):
        self.ops.append("ensure_tables")

    def deploy_views(self, sql_dir, params):
        self.ops.append(("views", params))
        return []

    def replace_table(self, table, rows):
        self.ops.append(("replace", table, len(rows)))
        self.tables[table] = rows

    def replace_partition(self, table, day, rows):
        self.ops.append(("partition", table, day.isoformat(), len(rows)))
        self.tables[table] = rows

    def upsert(self, table, rows, keys, keep_on_update=()):
        self.ops.append(("upsert", table, len(rows)))
        self.tables[table] = rows

    def append(self, table, rows):
        self.ops.append(("append", table, len(rows)))
        self.tables.setdefault(table, []).extend(rows)

    def existing_videos(self, ids):
        return {}

    def playlist_state(self):
        return getattr(self, "state", {})


def now_utc():
    return datetime.now(timezone.utc).replace(microsecond=0)
