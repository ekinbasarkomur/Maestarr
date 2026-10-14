"""The service container: every configured client, built once per process.

Unconfigured integrations are `None`; tools check for that and tell the user
what to set instead of failing.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from maestarr.clients.anilist import AniListClient
from maestarr.clients.arr import RadarrClient, SonarrClient, WhisparrClient
from maestarr.clients.base import HttpService, ServiceError
from maestarr.clients.history_sources import TraktClient
from maestarr.clients.jellyfin import JellyfinClient
from maestarr.clients.omdb import OmdbClient
from maestarr.clients.prowlarr import ProwlarrClient
from maestarr.clients.qbittorrent import QBittorrentClient
from maestarr.clients.stashdb import StashDbClient
from maestarr.clients.tmdb import TmdbClient
from maestarr import net
from maestarr.config import Settings, secret
from maestarr.domain import ServiceStatus
from maestarr.preferences import Preferences, load_preferences, save_preferences
from maestarr.torrent.resolve import ReleaseResolver

logger = logging.getLogger(__name__)


STATUS_TIMEOUT = 10.0


def metadata_client(s: Settings) -> Optional[TmdbClient]:
    """TMDB itself when a key is set, otherwise Seerr standing in for it."""
    from maestarr.language import metadata_code

    lang = metadata_code(s.MAESTARR_LANGUAGE)
    if secret(s.TMDB_API_KEY):
        return TmdbClient(secret(s.TMDB_API_KEY) or "", language=lang)
    if s.SEERR_URL and secret(s.SEERR_API_KEY):
        from maestarr.clients.seerr import SeerrMetadataClient

        return SeerrMetadataClient(s.SEERR_URL, secret(s.SEERR_API_KEY) or "", language=lang)
    return None


class NotConfigured(ServiceError):
    def __init__(self, service: str, hint: str):
        super().__init__(service, f"not configured — set {hint}")


@dataclass
class Services:
    settings: Settings
    sonarr: Optional[SonarrClient] = None
    radarr: Optional[RadarrClient] = None
    whisparr: Optional[WhisparrClient] = None
    prowlarr: Optional[ProwlarrClient] = None
    qbittorrent: Optional[QBittorrentClient] = None
    jellyfin: Optional[JellyfinClient] = None
    tmdb: Optional[TmdbClient] = None
    omdb: Optional[OmdbClient] = None
    anilist: Optional[AniListClient] = None
    trakt: Optional[TraktClient] = None
    stashdb: Optional[StashDbClient] = None
    resolver: ReleaseResolver = field(init=False)
    # Releases seen in recent searches (guid → candidate) and their latest
    # assessment; a grab must name a release the user has actually seen.
    releases: dict[str, Any] = field(default_factory=dict, init=False)
    assessments: dict[str, Any] = field(default_factory=dict, init=False)
    # Small in-process memo (TMDB details, taste profile) — key → (expires, value).
    memo: dict[str, Any] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self.resolver = ReleaseResolver(
            self.qbittorrent,
            probe_category=self.settings.QBITTORRENT_PROBE_CATEGORY,
            probe_timeout=self.settings.MAESTARR_PROBE_TIMEOUT,
        )

    @classmethod
    def from_settings(cls, s: Settings) -> "Services":
        def both(url: Optional[str], key: Any) -> bool:
            return bool(url) and bool(secret(key))

        net.configure(s)  # clients built below pick their proxy from it

        return cls(
            settings=s,
            sonarr=SonarrClient(s.SONARR_URL or "", secret(s.SONARR_API_KEY) or "")
            if both(s.SONARR_URL, s.SONARR_API_KEY)
            else None,
            radarr=RadarrClient(s.RADARR_URL or "", secret(s.RADARR_API_KEY) or "")
            if both(s.RADARR_URL, s.RADARR_API_KEY)
            else None,
            whisparr=WhisparrClient(s.WHISPARR_URL or "", secret(s.WHISPARR_API_KEY) or "")
            if s.MAESTARR_ADULT_CONTENT and both(s.WHISPARR_URL, s.WHISPARR_API_KEY)
            else None,
            prowlarr=ProwlarrClient(s.PROWLARR_URL or "", secret(s.PROWLARR_API_KEY) or "")
            if both(s.PROWLARR_URL, s.PROWLARR_API_KEY)
            else None,
            qbittorrent=QBittorrentClient(
                s.QBITTORRENT_URL,
                s.QBITTORRENT_USERNAME,
                secret(s.QBITTORRENT_PASSWORD),
                host_header=s.QBITTORRENT_HOST_HEADER,
            )
            if s.QBITTORRENT_URL
            else None,
            jellyfin=JellyfinClient(s.JELLYFIN_URL or "", secret(s.JELLYFIN_API_KEY) or "", s.JELLYFIN_USER)
            if both(s.JELLYFIN_URL, s.JELLYFIN_API_KEY)
            else None,
            tmdb=metadata_client(s),
            omdb=OmdbClient(secret(s.OMDB_API_KEY) or "") if secret(s.OMDB_API_KEY) else None,
            anilist=AniListClient(s.data_dir),
            trakt=TraktClient(secret(s.TRAKT_CLIENT_ID) or "") if secret(s.TRAKT_CLIENT_ID) else None,
            stashdb=StashDbClient(s.STASHDB_URL, secret(s.STASHDB_API_KEY) or "")
            if s.MAESTARR_ADULT_CONTENT and s.STASHDB_ENABLED and secret(s.STASHDB_API_KEY)
            else None,
        )

    # --- accessors that explain what is missing ---------------------------

    def need_sonarr(self) -> SonarrClient:
        if not self.sonarr:
            raise NotConfigured("sonarr", "SONARR_URL and SONARR_API_KEY")
        return self.sonarr

    def need_radarr(self) -> RadarrClient:
        if not self.radarr:
            raise NotConfigured("radarr", "RADARR_URL and RADARR_API_KEY")
        return self.radarr

    def need_whisparr(self) -> WhisparrClient:
        if not self.settings.MAESTARR_ADULT_CONTENT:
            raise ServiceError("whisparr", "adult content is switched off (Settings → Discovery)")
        if not self.whisparr:
            raise NotConfigured("whisparr", "WHISPARR_URL and WHISPARR_API_KEY")
        return self.whisparr

    def need_movie_app(self, app: str) -> RadarrClient:
        """Radarr or Whisparr — they share the movie API."""
        return self.need_whisparr() if app == "whisparr" else self.need_radarr()

    def need_qbittorrent(self) -> QBittorrentClient:
        if not self.qbittorrent:
            raise NotConfigured("qbittorrent", "QBITTORRENT_URL")
        return self.qbittorrent

    def need_tmdb(self) -> TmdbClient:
        if not self.tmdb:
            raise ServiceError(
                "tmdb", "no metadata source — connect Seerr or add a TMDB key under Settings → Discovery"
            )
        return self.tmdb

    def need_prowlarr(self) -> ProwlarrClient:
        if not self.prowlarr:
            raise NotConfigured("prowlarr", "PROWLARR_URL and PROWLARR_API_KEY")
        return self.prowlarr

    # --- preferences -------------------------------------------------------

    def preferences(self) -> Preferences:
        return load_preferences(self.settings.preferences_path)

    def save_preferences(self, prefs: Preferences) -> None:
        save_preferences(self.settings.preferences_path, prefs)

    # --- disk ---------------------------------------------------------------

    async def free_bytes(self, path: Optional[str]) -> Optional[int]:
        """Free space on the disk that holds `path`, as Sonarr/Radarr see it."""
        for app in (self.sonarr, self.radarr, self.whisparr):
            if not app:
                continue
            try:
                disks = await app.disk_space()
            except ServiceError:
                continue
            best = None
            for disk in disks:
                mount = disk.get("path", "")
                if path and path.startswith(mount) and (best is None or len(mount) > len(best.get("path", ""))):
                    best = disk
            if best is not None:
                return int(best.get("freeSpace", 0))
            if not path and disks:
                return min(int(d.get("freeSpace", 0)) for d in disks)
        return None

    # --- lifecycle -----------------------------------------------------------

    def clients(self) -> list[HttpService]:
        return [
            c
            for c in (
                self.sonarr, self.radarr, self.whisparr, self.prowlarr, self.qbittorrent, self.jellyfin,
                self.tmdb, self.omdb, self.anilist, self.trakt, self.stashdb,
            )
            if c is not None
        ]

    async def aclose(self) -> None:
        await asyncio.gather(*(c.aclose() for c in self.clients()), return_exceptions=True)

    async def status(self) -> list[ServiceStatus]:
        """Reachability of every integration (used by `doctor` and the UI)."""

        adult_off = not self.settings.MAESTARR_ADULT_CONTENT
        adult_saved = {
            "whisparr": bool(self.settings.WHISPARR_URL),
            "stashdb": bool(self.settings.STASHDB_ENABLED and secret(self.settings.STASHDB_API_KEY)),
        }

        async def check(name: str, client: Optional[HttpService], probe: Any) -> ServiceStatus:
            if client is None:
                if adult_off and adult_saved.get(name):
                    return ServiceStatus(name=name, configured=False, detail="18+ off")
                return ServiceStatus(name=name, configured=False)
            try:
                # A status page must answer quickly even when a service is crawling.
                version = await asyncio.wait_for(probe(), timeout=STATUS_TIMEOUT)
                return ServiceStatus(name=name, configured=True, ok=True, version=version)
            except asyncio.TimeoutError:
                return ServiceStatus(name=name, configured=True, ok=False, detail=f"no answer in {STATUS_TIMEOUT:.0f} s")
            except Exception as exc:  # noqa: BLE001 — report, never raise
                return ServiceStatus(name=name, configured=True, ok=False, detail=str(exc)[:200])

        async def arr_version(c: Any) -> str:
            return str((await c.system_status()).get("version"))

        checks = [
            check("sonarr", self.sonarr, lambda: arr_version(self.sonarr)),
            check("radarr", self.radarr, lambda: arr_version(self.radarr)),
            check("whisparr", self.whisparr, lambda: arr_version(self.whisparr)),
            check("prowlarr", self.prowlarr, lambda: arr_version(self.prowlarr)),
            check("qbittorrent", self.qbittorrent, lambda: self.qbittorrent.version()),  # type: ignore[union-attr]
            check("jellyfin", self.jellyfin, lambda: _jf_version(self.jellyfin)),
            check("tmdb", self.tmdb, lambda: _tmdb_ok(self.tmdb)),
            check("omdb", self.omdb, lambda: _omdb_ok(self.omdb)),
            check("trakt", self.trakt, lambda: _const("configured")),
            check("anilist", self.anilist, lambda: _const("public API")),
            check("stashdb", self.stashdb, lambda: _const("enabled")),
        ]
        return list(await asyncio.gather(*checks))


async def _const(value: str) -> str:
    return value


async def _jf_version(client: Any) -> str:
    info = await client.system_info()
    await client.user_id()
    return str(info.get("Version"))


async def _tmdb_ok(client: Any) -> str:
    await client.genres("movie")
    return "via Seerr" if client.name == "seerr" else "ok"


async def _omdb_ok(client: Any) -> str:
    rating, _ = await client.rating("tt0111161")
    if rating is None:
        raise ServiceError("omdb", "key rejected")
    return "ok"


_services: Optional[Services] = None


def get_services() -> Services:
    """Process-wide container (the API, MCP server and Telegram bot share it)."""
    global _services
    if _services is None:
        from maestarr.config import get_settings

        _services = Services.from_settings(get_settings())
    return _services


async def reset_services() -> None:
    global _services
    if _services is not None:
        await _services.aclose()
    _services = None
