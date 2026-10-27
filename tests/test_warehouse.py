from datetime import date

import sqlglot

from pipeline.warehouse import SCHEMAS, Warehouse


class FakeJob:
    def result(self):
        return []


class FakeClient:
    def __init__(self):
        self.queries, self.loads, self.deleted = [], [], []

    def query(self, sql, job_config=None):
        self.queries.append(sql)
        return FakeJob()

    def load_table_from_json(self, rows, destination, job_config=None):
        self.loads.append((destination, len(rows), job_config.write_disposition))
        return FakeJob()

    def delete_table(self, ref, not_found_ok=False):
        self.deleted.append(ref)

    def get_dataset(self, ref):
        if not getattr(self, "dataset_exists", True):
            from google.api_core.exceptions import NotFound
            raise NotFound("missing")
        return ref

    def create_dataset(self, ds, exists_ok=False):
        self.created = ds


def make():
    client = FakeClient()
    return Warehouse("proj", "ds", "US", client=client), client


def test_partition_load_targets_single_day():
    wh, client = make()
    wh.replace_partition("video_snapshots", date(2026, 10, 27), [{"video_id": "a"}])
    assert client.loads == [("proj.ds.video_snapshots$20261027", 1, "WRITE_TRUNCATE")]


def test_upsert_builds_valid_merge_and_dedupes():
    wh, client = make()
    rows = [{c.name: None for c in SCHEMAS["videos"]} | {"video_id": "a"} for _ in range(3)]
    wh.upsert("videos", rows, keys=["video_id"], keep_on_update=("first_seen_ts",))
    assert client.loads[0] == ("proj.ds._stg_videos", 1, "WRITE_TRUNCATE")
    sql = client.queries[0]
    sqlglot.parse_one(sql, read="bigquery")
    update_part = sql.split("UPDATE SET")[1].split("WHEN NOT MATCHED")[0]
    assert "first_seen_ts" not in update_part and "video_id =" not in update_part
    assert client.deleted == ["proj.ds._stg_videos"]


def test_empty_rows_do_nothing():
    wh, client = make()
    wh.upsert("videos", [], keys=["video_id"])
    wh.replace_partition("video_snapshots", date(2026, 10, 27), [])
    assert not client.loads and not client.queries


def test_views_render_without_placeholders(tmp_path):
    from pipeline.config import PROJECT_ROOT

    wh, client = make()
    names = wh.deploy_views(PROJECT_ROOT / "sql" / "views",
                            {"dataset_ref": "proj.ds", "timezone": "Asia/Colombo",
                             "default_category": "Other", "shorts_max_seconds": "180"})
    assert len(names) == len(client.queries) >= 15
    for sql in client.queries:
        assert "{{" not in sql
        sqlglot.parse_one(sql, read="bigquery")


def test_existing_dataset_is_not_recreated():
    wh, client = make()
    wh.ensure_dataset()
    assert not hasattr(client, "created")


def test_missing_dataset_is_created():
    wh, client = make()
    client.dataset_exists = False
    wh.ensure_dataset()
    assert client.created.location == "US"
