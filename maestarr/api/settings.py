"""Settings API — read, save and test every integration from the UI.

Secrets never leave the server: they come back as `{"set": true|false}`.
A PUT only touches the fields it sends; `null` clears a field (back to the
environment default). Tests run against the *candidate* values in the request
merged over what is saved, so the UI can test before saving.
"""

from __future__ import annotations

import asyncio
import secrets as pysecrets
from typing import Any, Awaitable, Callable, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, SecretStr, ValidationError

from maestarr.api.deps import require_setup_open, require_user
from maestarr.clients.base import ServiceError
from maestarr.config import SECRET_FIELDS, Settings, get_config_store, get_settings, reload_settings, secret

router = APIRouter(prefix="/api/settings", tags=["settings"])

SECTIONS: dict[str, list[str]] = {
    "ai": ["MAESTARR_LLM_PROVIDER", "MAESTARR_MODEL", "MAESTARR_LLM_API_KEY", "MAESTARR_MODEL_BASE_URL"],
    "jellyfin": ["JELLYFIN_URL", "JELLYFIN_API_KEY", "JELLYFIN_USER"],
    "sonarr": [
        "SONARR_URL", "SONARR_API_KEY", "SONARR_QUALITY_PROFILE", "SONARR_ROOT_FOLDER",
        "SONARR_ANIME_QUALITY_PROFILE", "SONARR_ANIME_ROOT_FOLDER",
    ],
    "radarr": ["RADARR_URL", "RADARR_API_KEY", "RADARR_QUALITY_PROFILE", "RADARR_ROOT_FOLDER"],
    "whisparr": ["WHISPARR_URL", "WHISPARR_API_KEY", "WHISPARR_QUALITY_PROFILE", "WHISPARR_ROOT_FOLDER"],
    "prowlarr": ["PROWLARR_URL", "PROWLARR_API_KEY"],
    "qbittorrent": ["QBITTORRENT_URL", "QBITTORRENT_USERNAME", "QBITTORRENT_PASSWORD", "QBITTORRENT_HOST_HEADER"],
    "tmdb": ["TMDB_API_KEY"],
    "omdb": ["OMDB_API_KEY"],
    "trakt": ["TRAKT_CLIENT_ID", "TRAKT_USERNAME"],
    "anilist": ["ANILIST_USERNAME"],
    "letterboxd": ["LETTERBOXD_EXPORT"],
    "stashdb": ["STASHDB_ENABLED", "STASHDB_API_KEY"],
    "telegram": ["TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_CHAT_IDS"],
    "behaviour": ["MAESTARR_ENRICH_TOP_N", "MAESTARR_PROBE_TIMEOUT", "MAESTARR_MIN_FREE_GB", "QBITTORRENT_PROBE_CATEGORY"],
}
EDITABLE = {f for fields in SECTIONS.values() for f in fields} | {"MAESTARR_SETUP_COMPLETE"}

# Called after every save; the app wires this to rebuild services and the bot.
_on_change: list[Callable[[], Awaitable[None]]] = []


def on_settings_change(callback: Callable[[], Awaitable[None]]) -> None:
    _on_change.append(callback)


def public_view(s: Settings) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for section, fields in SECTIONS.items():
        values: dict[str, Any] = {}
        for name in fields:
            value = getattr(s, name)
            if name in SECRET_FIELDS:
                values[name] = {"set": bool(secret(value))}
            else:
                values[name] = value
        out[section] = values
    return out


class SettingsUpdate(BaseModel):
    fields: dict[str, Any]


def _validate(update: dict[str, Any]) -> dict[str, Any]:
    unknown = set(update) - EDITABLE
    if unknown:
        raise HTTPException(status_code=422, detail=f"unknown or read-only settings: {', '.join(sorted(unknown))}")
    clean: dict[str, Any] = {}
    for name, value in update.items():
        if isinstance(value, str):
            value = value.strip()
            if value == "" and name in SECRET_FIELDS:
                continue  # empty secret box = keep the saved one
            if value == "":
                value = None
        clean[name] = value
    # Validate the merged result before saving anything.
    candidate = {k: v for k, v in clean.items() if v is not None}
    try:
        Settings(**{**_raw_current(), **candidate})
    except ValidationError as exc:
        first = exc.errors()[0]
        raise HTTPException(status_code=422, detail=f"{first['loc'][0]}: {first['msg']}") from exc
    return clean


def _raw_current() -> dict[str, Any]:
    """Saved values as plain JSON types (secrets unwrapped)."""
    return dict(get_config_store().values())


async def apply_update(update: dict[str, Any]) -> Settings:
    clean = _validate(update)
    get_config_store().update(clean)
    reload_settings()
    for callback in _on_change:
        await callback()
    return get_settings()


@router.get("")
async def read_settings(_: Any = Depends(require_setup_open)) -> dict[str, Any]:
    s = get_settings()
    return {"sections": public_view(s), "setup_complete": s.MAESTARR_SETUP_COMPLETE, "api_token_set": bool(secret(s.MAESTARR_API_TOKEN))}


@router.put("")
async def save_settings(body: SettingsUpdate, _: Any = Depends(require_setup_open)) -> dict[str, Any]:
    s = await apply_update(body.fields)
    return {"sections": public_view(s), "setup_complete": s.MAESTARR_SETUP_COMPLETE}


@router.post("/complete-setup")
async def complete_setup(_: Any = Depends(require_user)) -> dict[str, bool]:
    await apply_update({"MAESTARR_SETUP_COMPLETE": True})
    return {"setup_complete": True}


@router.post("/api-token")
async def regenerate_api_token(_: Any = Depends(require_user)) -> dict[str, str]:
    """Create (or replace) the API key for MCP clients and scripts. Shown once."""
    token = "mae_" + pysecrets.token_urlsafe(32)
    get_config_store().update({"MAESTARR_API_TOKEN": token})
    reload_settings()
    return {"token": token}


@router.delete("/api-token")
async def delete_api_token(_: Any = Depends(require_user)) -> dict[str, bool]:
    get_config_store().update({"MAESTARR_API_TOKEN": None})
    reload_settings()
    return {"deleted": True}


# --------------------------------------------------------------------------
# Connection tests
# --------------------------------------------------------------------------


class TestRequest(BaseModel):
    fields: dict[str, Any] = {}


def candidate_settings(fields: dict[str, Any]) -> Settings:
    current = get_settings()
    merged: dict[str, Any] = {}
    for name in Settings.model_fields:
        value = getattr(current, name)
        merged[name] = value.get_secret_value() if isinstance(value, SecretStr) else value
    for name, value in fields.items():
        if name not in Settings.model_fields:
            continue
        if isinstance(value, str):
            value = value.strip()
            if value == "" and name in SECRET_FIELDS:
                continue
            if value == "":
                value = None
        merged[name] = value
    return Settings(**{k: v for k, v in merged.items() if v is not None})


async def _arr_test(client: Any, kind: str) -> dict[str, Any]:
    status = await client.system_status()
    profiles, roots = await asyncio.gather(client.quality_profiles(), client.root_folders())
    if status.get("appName", "").lower() not in ("", kind):
        raise ServiceError(kind, f"that address is {status.get('appName')}, not {kind.capitalize()}")
    return {
        "version": status.get("version"),
        "quality_profiles": [p["name"] for p in profiles],
        "root_folders": [{"path": r["path"], "free_gb": round((r.get("freeSpace") or 0) / 1024**3)} for r in roots],
    }


async def run_test(service: str, s: Settings) -> dict[str, Any]:
    from maestarr.clients.anilist import AniListClient
    from maestarr.clients.arr import RadarrClient, SonarrClient, WhisparrClient
    from maestarr.clients.history_sources import TraktClient
    from maestarr.clients.jellyfin import JellyfinClient
    from maestarr.clients.omdb import OmdbClient
    from maestarr.clients.prowlarr import ProwlarrClient
    from maestarr.clients.qbittorrent import QBittorrentClient
    from maestarr.clients.stashdb import StashDbClient
    from maestarr.clients.tmdb import TmdbClient

    def need(*values: Optional[str]) -> None:
        if not all(values):
            raise ServiceError(service, "fill in the address and key first")

    if service in ("sonarr", "radarr", "whisparr"):
        url = getattr(s, f"{service.upper()}_URL")
        key = secret(getattr(s, f"{service.upper()}_API_KEY"))
        need(url, key)
        cls = {"sonarr": SonarrClient, "radarr": RadarrClient, "whisparr": WhisparrClient}[service]
        client = cls(url, key or "")
        try:
            return await _arr_test(client, service)
        finally:
            await client.aclose()
    if service == "prowlarr":
        need(s.PROWLARR_URL, secret(s.PROWLARR_API_KEY))
        client = ProwlarrClient(s.PROWLARR_URL or "", secret(s.PROWLARR_API_KEY) or "")
        try:
            status = await client.system_status()
            indexers = await client.indexers()
            return {"version": status.get("version"), "indexers": len([i for i in indexers if i.get("enable")])}
        finally:
            await client.aclose()
    if service == "qbittorrent":
        need(s.QBITTORRENT_URL)
        client = QBittorrentClient(
            s.QBITTORRENT_URL or "", s.QBITTORRENT_USERNAME, secret(s.QBITTORRENT_PASSWORD), host_header=s.QBITTORRENT_HOST_HEADER
        )
        try:
            version = await client.version()
            api = await client.webapi_version()
            return {
                "version": version,
                "metadata_lookup": "native (no torrent added)" if api >= (2, 15) else "probe (temporary torrent)",
                "categories": sorted((await client.categories()).keys()),
            }
        finally:
            await client.aclose()
    if service == "jellyfin":
        need(s.JELLYFIN_URL, secret(s.JELLYFIN_API_KEY))
        client = JellyfinClient(s.JELLYFIN_URL or "", secret(s.JELLYFIN_API_KEY) or "", s.JELLYFIN_USER)
        try:
            info = await client.system_info()
            users = await client.users()
            return {
                "version": info.get("Version"),
                "server_name": info.get("ServerName"),
                "users": [u.get("Name") for u in users if not (u.get("Policy") or {}).get("IsDisabled")],
            }
        finally:
            await client.aclose()
    if service == "tmdb":
        need(secret(s.TMDB_API_KEY))
        client = TmdbClient(secret(s.TMDB_API_KEY) or "")
        try:
            genres = await client.genres("movie")
            return {"version": "v3", "genres": len(genres)}
        finally:
            await client.aclose()
    if service == "omdb":
        need(secret(s.OMDB_API_KEY))
        client = OmdbClient(secret(s.OMDB_API_KEY) or "")
        try:
            rating, _ = await client.rating("tt0111161")
            if rating is None:
                raise ServiceError("omdb", "the key was rejected")
            return {"version": "ok", "sample": f"The Shawshank Redemption · IMDb {rating}"}
        finally:
            await client.aclose()
    if service == "trakt":
        need(secret(s.TRAKT_CLIENT_ID), s.TRAKT_USERNAME)
        client = TraktClient(secret(s.TRAKT_CLIENT_ID) or "")
        try:
            profile = await client.get_json(f"/users/{s.TRAKT_USERNAME}")
            return {"version": "ok", "user": profile.get("username")}
        finally:
            await client.aclose()
    if service == "anilist":
        need(s.ANILIST_USERNAME)
        client = AniListClient(s.data_dir)
        try:
            data = await client.query("query ($u: String) { User(name: $u) { id name } }", u=s.ANILIST_USERNAME)
            return {"version": "ok", "user": (data.get("User") or {}).get("name")}
        finally:
            await client.aclose()
    if service == "stashdb":
        need(secret(s.STASHDB_API_KEY))
        client = StashDbClient(s.STASHDB_URL, secret(s.STASHDB_API_KEY) or "")
        try:
            await client.search_performers("a", limit=1)
            return {"version": "ok"}
        finally:
            await client.aclose()
    if service == "telegram":
        need(secret(s.TELEGRAM_BOT_TOKEN))
        from aiogram import Bot

        bot = Bot(secret(s.TELEGRAM_BOT_TOKEN) or "")
        try:
            me = await bot.get_me()
            return {"version": "ok", "bot": f"@{me.username}"}
        except Exception as exc:  # noqa: BLE001
            raise ServiceError("telegram", f"token rejected: {exc}") from exc
        finally:
            await bot.session.close()
    if service == "ai":
        from pydantic_ai import Agent

        from maestarr.llm import ModelNotConfigured, build_model

        try:
            model = build_model(s)
        except ModelNotConfigured as exc:
            raise ServiceError("ai", str(exc)) from exc
        agent: Agent[None, str] = Agent(model, instructions="Reply with exactly one word.")
        try:
            result = await asyncio.wait_for(agent.run("Say: ready"), timeout=60)
        except asyncio.TimeoutError as exc:
            raise ServiceError("ai", "the model did not answer within 60 seconds") from exc
        except Exception as exc:  # noqa: BLE001 — provider errors vary wildly
            raise ServiceError("ai", _provider_error(exc)) from exc
        return {"version": "ok", "reply": str(result.output).strip()[:40]}
    raise HTTPException(status_code=404, detail=f"unknown service {service!r}")


def _provider_error(exc: Exception) -> str:
    text = str(exc)
    lowered = text.lower()
    if "401" in text or "authentication" in lowered or "api key" in lowered or "invalid x-api-key" in lowered:
        return "the API key was rejected"
    if "404" in text or "not found" in lowered or "does not exist" in lowered:
        return "the model name was not found for this provider"
    if "connect" in lowered:
        return "cannot reach the provider (check the address)"
    return text[:300]


@router.post("/test/{service}")
async def test_service(service: str, body: TestRequest, _: Any = Depends(require_setup_open)) -> dict[str, Any]:
    try:
        s = candidate_settings(body.fields)
    except ValidationError as exc:
        first = exc.errors()[0]
        return {"ok": False, "detail": f"{first['loc'][0]}: {first['msg']}"}
    try:
        result = await asyncio.wait_for(run_test(service, s), timeout=75)
    except asyncio.TimeoutError:
        return {"ok": False, "detail": "timed out — is the address right and the service up?"}
    except ServiceError as exc:
        return {"ok": False, "detail": str(exc).split(": ", 1)[-1]}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — report, never 500 on a test
        return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"[:300]}
    return {"ok": True, **result}
