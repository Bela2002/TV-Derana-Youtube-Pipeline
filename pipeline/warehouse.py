"""BigQuery storage: table creation, idempotent loads, MERGE upserts and view deployment.

Only batch load jobs are used (free in BigQuery) - no streaming inserts.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from google.api_core.exceptions import NotFound
from google.cloud import bigquery

log = logging.getLogger(__name__)
F = bigquery.SchemaField

SCHEMAS: dict[str, list[bigquery.SchemaField]] = {
    "channels": [
        F("channel_id", "STRING", "REQUIRED"),
        F("channel_title", "STRING"),
        F("custom_url", "STRING"),
        F("country", "STRING"),
        F("uploads_playlist_id", "STRING"),
        F("channel_created_at", "TIMESTAMP"),
        F("updated_at", "TIMESTAMP"),
    ],
    "channel_snapshots": [
        F("capture_date", "DATE", "REQUIRED", description="UTC date of the capture"),
        F("capture_ts", "TIMESTAMP", "REQUIRED", description="UTC timestamp of the capture"),
        F("channel_id", "STRING", "REQUIRED"),
        F("channel_title", "STRING"),
        F("subscriber_count", "INT64", description="Public (rounded) subscriber count"),
        F("hidden_subscriber_count", "BOOL"),
        F("view_count", "INT64", description="Lifetime channel views"),
        F("video_count", "INT64"),
    ],
    "videos": [
        F("video_id", "STRING", "REQUIRED"),
        F("channel_id", "STRING"),
        F("channel_title", "STRING"),
        F("title", "STRING"),
        F("published_at", "TIMESTAMP"),
        F("duration_iso", "STRING"),
        F("duration_seconds", "INT64"),
        F("definition", "STRING"),
        F("youtube_category_id", "STRING"),
        F("default_audio_language", "STRING"),
        F("live_broadcast_content", "STRING"),
        F("is_short", "BOOL"),
        F("format_method", "STRING", description="How is_short was decided: playlist, url, duration, live, unknown"),
        F("video_format", "STRING", description="Short, Long-form, Live / Upcoming, Unknown"),
        F("tags", "STRING"),
        F("first_seen_ts", "TIMESTAMP"),
        F("last_seen_ts", "TIMESTAMP"),
    ],
    "video_snapshots": [
        F("capture_date", "DATE", "REQUIRED"),
        F("capture_ts", "TIMESTAMP", "REQUIRED"),
        F("channel_id", "STRING"),
        F("video_id", "STRING", "REQUIRED"),
        F("view_count", "INT64"),
        F("like_count", "INT64"),
        F("comment_count", "INT64"),
    ],
    "playlists": [
        F("playlist_id", "STRING", "REQUIRED"),
        F("channel_id", "STRING"),
        F("playlist_title", "STRING"),
        F("item_count", "INT64"),
        F("playlist_created_at", "TIMESTAMP"),
        F("updated_at", "TIMESTAMP"),
        F("last_scanned_at", "TIMESTAMP", description="Last time every item of the playlist was read"),
    ],
    "video_playlists": [
        F("video_id", "STRING", "REQUIRED"),
        F("playlist_id", "STRING", "REQUIRED"),
        F("first_seen_ts", "TIMESTAMP"),
        F("last_seen_ts", "TIMESTAMP"),
    ],
    "category_rules": [
        F("priority", "INT64", "REQUIRED"),
        F("category", "STRING", "REQUIRED"),
        F("program", "STRING"),
        F("pattern", "STRING", "REQUIRED"),
    ],
    "pipeline_runs": [
        F("run_id", "STRING", "REQUIRED"),
        F("started_at", "TIMESTAMP"),
        F("finished_at", "TIMESTAMP"),
        F("status", "STRING"),
        F("capture_date", "DATE"),
        F("channel_id", "STRING"),
        F("videos_tracked", "INT64"),
        F("new_videos", "INT64"),
        F("playlists", "INT64"),
        F("api_units_used", "INT64"),
        F("message", "STRING"),
    ],
}

PARTITIONED = {"channel_snapshots": "capture_date", "video_snapshots": "capture_date"}
CLUSTERED = {"video_snapshots": ["video_id"], "videos": ["video_id"], "video_playlists": ["video_id"]}


class Warehouse:
    def __init__(self, project: str, dataset: str, location: str, client: bigquery.Client | None = None):
        self.project = project
        self.dataset = dataset
        self.location = location
        self.client = client or bigquery.Client(project=project, location=location)

    @property
    def dataset_ref(self) -> str:
        return f"{self.project}.{self.dataset}"

    def table_ref(self, name: str) -> str:
        return f"{self.dataset_ref}.{name}"

    # ----------------------------------------------------------------- setup
    def ensure_dataset(self) -> None:
        # Check first: on Cloud Run the service account only has access to this one dataset
        # (no project-wide create permission), so an existing dataset must not trigger a create.
        try:
            self.client.get_dataset(self.dataset_ref)
            return
        except NotFound:
            pass
        ds = bigquery.Dataset(self.dataset_ref)
        ds.location = self.location
        ds.description = "Daily YouTube performance data (Data API v3 snapshots)"
        self.client.create_dataset(ds, exists_ok=True)

    def ensure_tables(self) -> None:
        for name, schema in SCHEMAS.items():
            ref = self.table_ref(name)
            try:
                table = self.client.get_table(ref)
            except NotFound:
                table = bigquery.Table(ref, schema=schema)
                if name in PARTITIONED:
                    table.time_partitioning = bigquery.TimePartitioning(
                        type_=bigquery.TimePartitioningType.DAY, field=PARTITIONED[name]
                    )
                if name in CLUSTERED:
                    table.clustering_fields = CLUSTERED[name]
                self.client.create_table(table)
                log.info("Created table %s", ref)
                continue
            # additive schema evolution: append columns that are new in code
            existing = {f.name for f in table.schema}
            missing = [f for f in schema if f.name not in existing]
            if missing:
                nullable = [F(f.name, f.field_type, "NULLABLE", description=f.description) for f in missing]
                table.schema = list(table.schema) + nullable
                self.client.update_table(table, ["schema"])
                log.info("Added columns %s to %s", [f.name for f in missing], ref)

    def deploy_views(self, sql_dir: Path, params: dict[str, str]) -> list[str]:
        created = []
        for path in sorted(Path(sql_dir).glob("*.sql")):
            sql = path.read_text(encoding="utf-8")
            for key, value in params.items():
                sql = sql.replace("{{" + key + "}}", value)
            self.client.query(sql).result()
            created.append(path.stem)
        return created

    # ----------------------------------------------------------------- loads
    def _load(self, destination: str, schema, rows: list[dict], disposition: str) -> None:
        config = bigquery.LoadJobConfig(
            schema=schema,
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            write_disposition=disposition,
        )
        self.client.load_table_from_json(rows, destination, job_config=config).result()

    def replace_partition(self, table: str, partition_day: date, rows: list[dict]) -> None:
        """Idempotent daily load: re-running on the same UTC day replaces that day's rows."""
        if not rows:
            return
        destination = f"{self.table_ref(table)}${partition_day.strftime('%Y%m%d')}"
        self._load(destination, SCHEMAS[table], rows, bigquery.WriteDisposition.WRITE_TRUNCATE)

    def replace_table(self, table: str, rows: list[dict]) -> None:
        if not rows:
            return
        self._load(self.table_ref(table), SCHEMAS[table], rows, bigquery.WriteDisposition.WRITE_TRUNCATE)

    def append(self, table: str, rows: list[dict]) -> None:
        if rows:
            self._load(self.table_ref(table), SCHEMAS[table], rows, bigquery.WriteDisposition.WRITE_APPEND)

    def upsert(self, table: str, rows: list[dict], keys: list[str], keep_on_update: tuple[str, ...] = ()) -> None:
        """Load rows to a staging table, then MERGE into the target on the key columns."""
        if not rows:
            return
        deduped: dict[tuple, dict] = {}
        for row in rows:
            deduped[tuple(row[k] for k in keys)] = row
        rows = list(deduped.values())
        staging = f"_stg_{table}"
        self._load(self.table_ref(staging), SCHEMAS[table], rows, bigquery.WriteDisposition.WRITE_TRUNCATE)
        columns = [f.name for f in SCHEMAS[table]]
        on = " AND ".join(f"T.{k} = S.{k}" for k in keys)
        updates = ", ".join(f"{c} = S.{c}" for c in columns if c not in keys and c not in keep_on_update)
        insert_cols = ", ".join(columns)
        insert_vals = ", ".join(f"S.{c}" for c in columns)
        sql = f"""
            MERGE `{self.table_ref(table)}` T
            USING `{self.table_ref(staging)}` S
            ON {on}
            WHEN MATCHED THEN UPDATE SET {updates}
            WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_vals})
        """
        self.client.query(sql).result()
        self.client.delete_table(self.table_ref(staging), not_found_ok=True)

    # --------------------------------------------------------------- lookups
    def playlist_state(self) -> dict:
        """{playlist_id: (item_count, last_scanned_at)} from the previous run."""
        job = self.client.query(
            f"SELECT playlist_id, item_count, last_scanned_at FROM `{self.table_ref('playlists')}`"
        )
        return {row.playlist_id: (row.item_count, row.last_scanned_at) for row in job.result()}

    def existing_videos(self, video_ids: list[str]) -> dict[str, tuple[bool | None, str]]:
        """{video_id: (is_short, format_method)} for videos already stored."""
        if not video_ids:
            return {}
        job = self.client.query(
            f"SELECT video_id, is_short, format_method FROM `{self.table_ref('videos')}` "
            "WHERE video_id IN UNNEST(@ids)",
            job_config=bigquery.QueryJobConfig(
                query_parameters=[bigquery.ArrayQueryParameter("ids", "STRING", video_ids)]
            ),
        )
        return {row.video_id: (row.is_short, row.format_method or "") for row in job.result()}
