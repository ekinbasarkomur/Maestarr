"""Maestarr configuration — environment variables and `.env`.

Every integration is optional: a service whose URL (or key) is unset is simply
reported as "not configured" by `maestarr doctor` and its tools stay hidden
from the agent. That is what lets one image serve very different stacks.

Settings are read once and cached via get_settings(). Tests that monkeypatch the
environment must call get_settings.cache_clear() first; the clear_settings_cache
fixture in tests/conftest.py does this automatically.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Annotated, Optional

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Logging ---
    MAESTARR_LOG_LEVEL: str = "INFO"
    # Absolute path; defaults to <project_root>/logs when unset.
    MAESTARR_LOG_DIR: Optional[str] = None

    # --- HTTP server ---
    MAESTARR_HOST: str = "127.0.0.1"
    MAESTARR_PORT: int = 8709
    # Optional shared secret for the web UI / HTTP API. When set, every /api
    # request must send `Authorization: Bearer <token>`.
    MAESTARR_API_TOKEN: Optional[SecretStr] = None

    # --- State ---
    # SQLite database (conversations, pending approvals) and preferences.
    MAESTARR_DATA_DIR: str = "data"
    MAESTARR_PREFERENCES_FILE: Optional[str] = None

    # --- LLM (pydantic-ai model id) ---
    # e.g. "anthropic:claude-sonnet-5-5", "openai:gpt-5.4", "ollama:qwen3:14b".
    # Provider keys come from the provider's own env var (ANTHROPIC_API_KEY,
    # OPENAI_API_KEY, ...), which pydantic-ai reads itself.
    MAESTARR_MODEL: str = "anthropic:claude-sonnet-5-5"
    # Base URL for an OpenAI-compatible server (Ollama, LM Studio, vLLM,
    # OpenRouter). Used when MAESTARR_MODEL starts with "ollama:" or "openai-compat:".
    MAESTARR_MODEL_BASE_URL: Optional[str] = None
    MAESTARR_MODEL_API_KEY: Optional[SecretStr] = None

    # --- *arr stack ---
    SONARR_URL: Optional[str] = None
    SONARR_API_KEY: Optional[SecretStr] = None
    RADARR_URL: Optional[str] = None
    RADARR_API_KEY: Optional[SecretStr] = None
    PROWLARR_URL: Optional[str] = None
    PROWLARR_API_KEY: Optional[SecretStr] = None

    # --- Download client ---
    QBITTORRENT_URL: Optional[str] = None
    QBITTORRENT_USERNAME: Optional[str] = None
    QBITTORRENT_PASSWORD: Optional[SecretStr] = None
    # Some port maps need this (qBittorrent validates the Host header against
    # the Web UI's own address), e.g. "localhost:8080".
    QBITTORRENT_HOST_HEADER: Optional[str] = None
    # Category used for metadata probes; probes are added stopped and removed.
    QBITTORRENT_PROBE_CATEGORY: str = "maestarr-probe"

    # --- Media server (watch history) ---
    JELLYFIN_URL: Optional[str] = None
    JELLYFIN_API_KEY: Optional[SecretStr] = None
    # User whose history drives recommendations; first administrator when unset.
    JELLYFIN_USER: Optional[str] = None

    # --- Metadata sources ---
    TMDB_API_KEY: Optional[SecretStr] = None  # v3 key or v4 read-access token
    OMDB_API_KEY: Optional[SecretStr] = None  # IMDb ratings
    TRAKT_CLIENT_ID: Optional[SecretStr] = None
    TRAKT_USERNAME: Optional[str] = None
    ANILIST_USERNAME: Optional[str] = None  # AniList needs no key for public data
    # Path to a Letterboxd data export (the unzipped folder or the .zip).
    LETTERBOXD_EXPORT: Optional[str] = None
    # Adult scene database. Off unless explicitly enabled AND a key is set.
    STASHDB_ENABLED: bool = False
    STASHDB_API_KEY: Optional[SecretStr] = None
    STASHDB_URL: str = "https://stashdb.org/graphql"

    # --- Telegram ---
    TELEGRAM_BOT_TOKEN: Optional[SecretStr] = None
    # Comma-separated chat ids allowed to talk to the bot. Empty = nobody.
    TELEGRAM_ALLOWED_CHAT_IDS: Annotated[list[int], NoDecode] = Field(default_factory=list)

    # --- Behaviour ---
    # How many top candidates get the expensive enrichment (file list + swarm).
    MAESTARR_ENRICH_TOP_N: int = 6
    # Seconds to wait for a magnet's metadata during a probe.
    MAESTARR_PROBE_TIMEOUT: float = 60.0
    # Warn about plans that would leave less than this much free space (GiB).
    MAESTARR_MIN_FREE_GB: float = 50.0

    @field_validator("TELEGRAM_ALLOWED_CHAT_IDS", mode="before")
    @classmethod
    def _split_ids(cls, value: object) -> object:
        if isinstance(value, str):
            return [int(part) for part in value.replace(" ", "").split(",") if part]
        if isinstance(value, int):
            return [value]
        return value

    @property
    def data_dir(self) -> Path:
        path = Path(self.MAESTARR_DATA_DIR).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def database_path(self) -> Path:
        return self.data_dir / "maestarr.sqlite3"

    @property
    def preferences_path(self) -> Path:
        if self.MAESTARR_PREFERENCES_FILE:
            return Path(self.MAESTARR_PREFERENCES_FILE).expanduser()
        return self.data_dir / "preferences.json"


def secret(value: Optional[SecretStr]) -> Optional[str]:
    """Unwrap an optional secret.

    >>> secret(None) is None
    True
    >>> secret(SecretStr("k"))
    'k'
    """
    return value.get_secret_value() if value is not None else None


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings singleton."""
    return Settings()
