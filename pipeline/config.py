"""Runtime configuration, read from environment variables (and a local .env file if present)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent



def _load_env_file(path: Path) -> None:
    """Load KEY=VALUE lines from .env without overriding real environment variables."""
    if not path.is_file():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(path, override=False)
        return
    except ImportError:  # minimal fallback parser
        pass
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


_load_env_file(PROJECT_ROOT / ".env")  # Cloud Run has no .env and uses real env vars


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer, got {raw!r}") from exc


def _detect_project() -> str | None:
    project = _env("GCP_PROJECT_ID") or _env("GOOGLE_CLOUD_PROJECT")
    if project:
        return project
    try:
        import google.auth

        _, project = google.auth.default()
        return project
    except Exception:  # pragma: no cover - only hit when no credentials exist
        return None


@dataclass(frozen=True)
class Settings:
    youtube_api_key: str | None
    channel_id: str | None
    channel_handle: str | None
    gcp_project: str | None
    bq_dataset: str
    bq_location: str
    lookback_days: int
    playlist_page_budget: int
    playlist_rescan_days: int
    playlist_max_pages: int
    shorts_detection: tuple[str, ...]
    shorts_max_seconds: int
    report_timezone: str
    rules_path: Path
    sql_dir: Path = field(default=PROJECT_ROOT / "sql" / "views")

    def require_youtube(self) -> None:
        if not self.youtube_api_key:
            raise RuntimeError("YOUTUBE_API_KEY is not set.")
        if not (self.channel_id or self.channel_handle):
            raise RuntimeError("Set CHANNEL_ID or CHANNEL_HANDLE.")

    def require_bigquery(self) -> None:
        if not self.gcp_project:
            raise RuntimeError(
                "GCP project not found. Set GCP_PROJECT_ID or run "
                "'gcloud auth application-default login'."
            )


def load_settings() -> Settings:
    detection = _env("SHORTS_DETECTION", "playlist,url,duration") or ""
    methods = tuple(m.strip().lower() for m in detection.split(",") if m.strip())
    unknown = set(methods) - {"playlist", "url", "duration"}
    if unknown:
        raise ValueError(f"Unknown SHORTS_DETECTION method(s): {', '.join(sorted(unknown))}")

    rules = _env("CATEGORY_RULES_PATH")
    rules_path = Path(rules) if rules else PROJECT_ROOT / "config" / "category_rules.json"

    return Settings(
        youtube_api_key=_env("YOUTUBE_API_KEY"),
        channel_id=_env("CHANNEL_ID"),
        channel_handle=_env("CHANNEL_HANDLE", "@tvderanaofficial"),
        gcp_project=_detect_project(),
        bq_dataset=_env("BQ_DATASET", "youtube_derana") or "youtube_derana",
        bq_location=_env("BQ_LOCATION", "US") or "US",
        lookback_days=_env_int("LOOKBACK_DAYS", 90),
        playlist_page_budget=_env_int("PLAYLIST_PAGE_BUDGET", 3000),
        playlist_rescan_days=_env_int("PLAYLIST_RESCAN_DAYS", 7),
        playlist_max_pages=_env_int("PLAYLIST_MAX_PAGES", 4),
        shorts_detection=methods or ("duration",),
        shorts_max_seconds=_env_int("SHORTS_MAX_SECONDS", 180),
        report_timezone=_env("REPORT_TIMEZONE", "Asia/Colombo") or "Asia/Colombo",
        rules_path=rules_path,
    )
