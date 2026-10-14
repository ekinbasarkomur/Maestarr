"""Maestarr configuration.

Two layers:

1. Environment variables / `.env` — the starting point, and the ONLY source for
   bootstrap values (data dir, host, port, logging).
2. The `config` table in the SQLite database — everything saved from the UI
   (onboarding wizard, Settings page). It overrides layer 1.

`get_settings()` merges them and caches the result; `reload_settings()` drops
the caches after the UI saved something so the next request sees it.
Every integration is optional: an unset URL/key simply hides its tools.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Annotated, Any, Literal, Optional

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

LlmProvider = Literal["anthropic", "openai", "google", "openrouter", "ollama", "openai-compat"]


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Bootstrap (environment only) ---
    MAESTARR_LOG_LEVEL: str = "INFO"
    MAESTARR_LOG_DIR: Optional[str] = None
    MAESTARR_HOST: str = "127.0.0.1"
    MAESTARR_PORT: int = 8709
    MAESTARR_DATA_DIR: str = "data"

    # --- Instance ---
    MAESTARR_SETUP_COMPLETE: bool = False
    # API key for MCP clients and scripts (Authorization: Bearer ...). The web
    # UI uses a login session instead. Generated from Settings → API.
    MAESTARR_API_TOKEN: Optional[SecretStr] = None
    MAESTARR_PREFERENCES_FILE: Optional[str] = None

    # --- LLM ---
    MAESTARR_LLM_PROVIDER: LlmProvider = "anthropic"
    # Model name for the provider, e.g. "claude-sonnet-5-5", "gpt-5.4",
    # "gemini-3.1-pro-preview", "qwen3:14b". A legacy "provider:model" value
    # is understood too.
    MAESTARR_MODEL: str = "claude-sonnet-5-5"
    MAESTARR_LLM_API_KEY: Optional[SecretStr] = None
    # Ollama / OpenAI-compatible servers (LM Studio, vLLM, LiteLLM ...).
    MAESTARR_MODEL_BASE_URL: Optional[str] = None

    # --- *arr stack ---
    SONARR_URL: Optional[str] = None
    SONARR_API_KEY: Optional[SecretStr] = None
    SONARR_QUALITY_PROFILE: Optional[str] = None
    SONARR_ROOT_FOLDER: Optional[str] = None
    SONARR_ANIME_QUALITY_PROFILE: Optional[str] = None
    SONARR_ANIME_ROOT_FOLDER: Optional[str] = None
    RADARR_URL: Optional[str] = None
    RADARR_API_KEY: Optional[SecretStr] = None
    RADARR_QUALITY_PROFILE: Optional[str] = None
    RADARR_ROOT_FOLDER: Optional[str] = None
    # Whisparr v3 (adult). Its tools only appear when this is configured.
    WHISPARR_URL: Optional[str] = None
    WHISPARR_API_KEY: Optional[SecretStr] = None
    WHISPARR_QUALITY_PROFILE: Optional[str] = None
    WHISPARR_ROOT_FOLDER: Optional[str] = None
    PROWLARR_URL: Optional[str] = None
    PROWLARR_API_KEY: Optional[SecretStr] = None

    # --- Download client ---
    QBITTORRENT_URL: Optional[str] = None
    QBITTORRENT_USERNAME: Optional[str] = None
    QBITTORRENT_PASSWORD: Optional[SecretStr] = None
    # Some port maps need this (qBittorrent validates the Host header against
    # the Web UI's own address), e.g. "localhost:8080".
    QBITTORRENT_HOST_HEADER: Optional[str] = None
    QBITTORRENT_PROBE_CATEGORY: str = "maestarr-probe"

    # --- Media server (watch history) ---
    JELLYFIN_URL: Optional[str] = None
    JELLYFIN_API_KEY: Optional[SecretStr] = None
    JELLYFIN_USER: Optional[str] = None

    # --- Metadata sources ---
    TMDB_API_KEY: Optional[SecretStr] = None
    OMDB_API_KEY: Optional[SecretStr] = None
    TRAKT_CLIENT_ID: Optional[SecretStr] = None
    TRAKT_USERNAME: Optional[str] = None
    ANILIST_USERNAME: Optional[str] = None
    LETTERBOXD_EXPORT: Optional[str] = None
    STASHDB_ENABLED: bool = False
    STASHDB_API_KEY: Optional[SecretStr] = None
    STASHDB_URL: str = "https://stashdb.org/graphql"

    # --- Telegram ---
    TELEGRAM_BOT_TOKEN: Optional[SecretStr] = None
    TELEGRAM_ALLOWED_CHAT_IDS: Annotated[list[int], NoDecode] = Field(default_factory=list)

    # --- Behaviour ---
    MAESTARR_ENRICH_TOP_N: int = 6
    MAESTARR_PROBE_TIMEOUT: float = 60.0
    MAESTARR_MIN_FREE_GB: float = 50.0

    @field_validator("TELEGRAM_ALLOWED_CHAT_IDS", mode="before")
    @classmethod
    def _split_ids(cls, value: object) -> object:
        if isinstance(value, str):
            return [int(part) for part in value.replace(" ", "").split(",") if part]
        if isinstance(value, int):
            return [value]
        return value

    @field_validator(
        "SONARR_URL", "RADARR_URL", "WHISPARR_URL", "PROWLARR_URL", "QBITTORRENT_URL",
        "JELLYFIN_URL", "MAESTARR_MODEL_BASE_URL", mode="before",
    )
    @classmethod
    def _clean_url(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip().rstrip("/")
            return value or None
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


SECRET_FIELDS = {
    name for name, field in Settings.model_fields.items()
    if field.annotation is not None and "SecretStr" in str(field.annotation)
}


@functools.lru_cache(maxsize=1)
def get_config_store() -> "Any":
    from maestarr.configstore import ConfigStore

    env = Settings()
    return ConfigStore(env.database_path)


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Environment merged with UI-saved values (the database wins)."""
    from maestarr.configstore import BOOTSTRAP_ONLY

    env = Settings()
    try:
        saved = get_config_store().values()
    except Exception:  # noqa: BLE001 — an unreadable DB must not stop the CLI
        return env
    overrides = {k: v for k, v in saved.items() if k in Settings.model_fields and k not in BOOTSTRAP_ONLY}
    if not overrides:
        return env
    # Init kwargs have the highest priority in pydantic-settings.
    return Settings(**overrides)


def reload_settings() -> None:
    """Forget cached settings, services and the agent after a settings change."""
    get_settings.cache_clear()
    try:
        from maestarr.agent.agent import get_agent

        get_agent.cache_clear()
    except ImportError:  # pragma: no cover
        pass
