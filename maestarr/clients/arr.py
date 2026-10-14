"""Sonarr and Radarr clients (API v3 — Sonarr v4 and Radarr v5 still serve it).

Both apps share most of their API surface (system, queue, commands, manual
import, interactive release search), so the shared part lives in `ArrClient`
and only the series/movie specific endpoints differ.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

import httpx

from maestarr.clients.base import HttpService, ServiceError
from maestarr.domain import ReleaseCandidate

ImportMode = Literal["auto", "move", "copy"]


RELEASE_SEARCH_TIMEOUT = 1800.0


class ArrClient(HttpService):
    app: Literal["sonarr", "radarr", "whisparr"]

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        super().__init__(
            base_url,
            headers={"X-Api-Key": api_key, "Accept": "application/json"},
            # Interactive searches fan out to every indexer and routinely take
            # one to three minutes on a busy stack.
            timeout=httpx.Timeout(240.0, connect=10.0),
            transport=transport,
        )

    # --- system ---------------------------------------------------------

    async def system_status(self) -> dict[str, Any]:
        return await self.get_json("/api/v3/system/status")

    async def quality_profiles(self) -> list[dict[str, Any]]:
        return await self.get_json("/api/v3/qualityprofile")

    async def root_folders(self) -> list[dict[str, Any]]:
        return await self.get_json("/api/v3/rootfolder")

    async def tags(self) -> list[dict[str, Any]]:
        return await self.get_json("/api/v3/tag")

    async def disk_space(self) -> list[dict[str, Any]]:
        return await self.get_json("/api/v3/diskspace")

    # --- queue / history -----------------------------------------------

    async def queue(self, page_size: int = 200) -> list[dict[str, Any]]:
        data = await self.get_json(
            "/api/v3/queue",
            pageSize=page_size,
            includeUnknownSeriesItems="true" if self.app == "sonarr" else None,
            includeUnknownMovieItems="true" if self.app in ("radarr", "whisparr") else None,
        )
        return (data or {}).get("records", [])

    async def remove_queue_item(
        self, queue_id: int, *, remove_from_client: bool = True, blocklist: bool = False
    ) -> None:
        await self.delete(
            f"/api/v3/queue/{queue_id}",
            removeFromClient=str(remove_from_client).lower(),
            blocklist=str(blocklist).lower(),
        )

    async def history(self, page_size: int = 50) -> list[dict[str, Any]]:
        data = await self.get_json(
            "/api/v3/history", pageSize=page_size, sortKey="date", sortDirection="descending"
        )
        return (data or {}).get("records", [])

    # --- commands --------------------------------------------------------

    async def command(self, name: str, **body: Any) -> dict[str, Any]:
        return await self.post_json("/api/v3/command", {"name": name, **body})

    async def command_status(self, command_id: int) -> dict[str, Any]:
        return await self.get_json(f"/api/v3/command/{command_id}")

    # --- interactive search ----------------------------------------------

    async def releases(self, **params: Any) -> list[ReleaseCandidate]:
        # A season search fans out to every indexer (one query per episode for
        # anime) and the app then scores every release; on a busy host a movie
        # with 150 releases took over 15 minutes.
        clean = {k: v for k, v in params.items() if v is not None}
        try:
            response = await self.request(
                "GET", "/api/v3/release", params=clean, timeout=httpx.Timeout(RELEASE_SEARCH_TIMEOUT, connect=10.0)
            )
        except ServiceError as exc:
            if "timed out" in str(exc):
                raise ServiceError(
                    self.name,
                    f"the release search took longer than {RELEASE_SEARCH_TIMEOUT / 60:.0f} minutes; "
                    f"{self.name.capitalize()} is still working, try again in a few minutes",
                ) from exc
            raise
        raw = response.json() if response.content else []
        return [release_from_arr(self.app, item) for item in raw or []]

    async def grab(
        self,
        release: ReleaseCandidate,
        *,
        series_id: Optional[int] = None,
        episode_ids: Optional[list[int]] = None,
        movie_id: Optional[int] = None,
    ) -> dict[str, Any]:
        """Send a release from the app's search cache to the download client.

        The cache key is `indexerId_guid` with a 30-minute TTL, so the release
        must come from a recent `releases()` call on this same app (a 404 means
        "search again"). Passing `series_id`+`episode_ids` (Sonarr) or
        `movie_id` (Radarr) overrides the app's own mapping — the way to grab a
        release it rejected as "Unable to identify". An override needs the
        release's quality and languages too, which `release` carries.
        """
        body: dict[str, Any] = {"guid": release.guid, "indexerId": release.indexer_id}
        override = (series_id is not None and episode_ids) or movie_id is not None
        if override:
            body["shouldOverride"] = True
            body["quality"] = release.quality_raw
            body["languages"] = release.languages_raw or [{"id": 1, "name": "English"}]
            if series_id is not None:
                body["seriesId"] = series_id
                body["episodeIds"] = episode_ids
            if movie_id is not None:
                body["movieId"] = movie_id
        return await self.post_json("/api/v3/release", body)

    # --- manual import ---------------------------------------------------

    async def manual_import_scan(
        self,
        *,
        folder: Optional[str] = None,
        download_id: Optional[str] = None,
        series_id: Optional[int] = None,
        movie_id: Optional[int] = None,
        filter_existing: bool = False,
    ) -> list[dict[str, Any]]:
        return await self.get_json(
            "/api/v3/manualimport",
            folder=folder,
            downloadId=download_id,
            seriesId=series_id,
            movieId=movie_id,
            filterExistingFiles=str(filter_existing).lower(),
        )

    async def manual_import(
        self, files: list[dict[str, Any]], *, import_mode: ImportMode = "auto"
    ) -> dict[str, Any]:
        return await self.command("ManualImport", files=files, importMode=import_mode)


class SonarrClient(ArrClient):
    name = "sonarr"
    app = "sonarr"

    async def series(self) -> list[dict[str, Any]]:
        return await self.get_json("/api/v3/series")

    async def series_by_id(self, series_id: int) -> dict[str, Any]:
        return await self.get_json(f"/api/v3/series/{series_id}")

    async def lookup(self, term: str) -> list[dict[str, Any]]:
        return await self.get_json("/api/v3/series/lookup", term=term)

    async def add_series(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.post_json("/api/v3/series", payload)

    async def episodes(self, series_id: int) -> list[dict[str, Any]]:
        return await self.get_json("/api/v3/episode", seriesId=series_id)

    async def episode_files(self, series_id: int) -> list[dict[str, Any]]:
        return await self.get_json("/api/v3/episodefile", seriesId=series_id)

    async def delete_episode_files(self, file_ids: list[int]) -> None:
        await self.request(
            "DELETE", "/api/v3/episodefile/bulk", json={"episodeFileIds": file_ids}
        )

    async def set_episodes_monitored(self, episode_ids: list[int], monitored: bool) -> None:
        await self.put_json(
            "/api/v3/episode/monitor", {"episodeIds": episode_ids, "monitored": monitored}
        )

    async def search_season(self, series_id: int, season_number: int) -> dict[str, Any]:
        return await self.command("SeasonSearch", seriesId=series_id, seasonNumber=season_number)

    async def search_episodes(self, episode_ids: list[int]) -> dict[str, Any]:
        return await self.command("EpisodeSearch", episodeIds=episode_ids)

    async def search_series(self, series_id: int) -> dict[str, Any]:
        return await self.command("SeriesSearch", seriesId=series_id)

    async def wanted_missing(self, page_size: int = 100) -> list[dict[str, Any]]:
        data = await self.get_json(
            "/api/v3/wanted/missing", pageSize=page_size, includeSeries="true"
        )
        return (data or {}).get("records", [])


class RadarrClient(ArrClient):
    name = "radarr"
    app = "radarr"

    async def movies(self) -> list[dict[str, Any]]:
        return await self.get_json("/api/v3/movie")

    async def movie_by_id(self, movie_id: int) -> dict[str, Any]:
        return await self.get_json(f"/api/v3/movie/{movie_id}")

    async def lookup(self, term: str) -> list[dict[str, Any]]:
        return await self.get_json("/api/v3/movie/lookup", term=term)

    async def lookup_tmdb(self, tmdb_id: int) -> dict[str, Any]:
        return await self.get_json("/api/v3/movie/lookup/tmdb", tmdbId=tmdb_id)

    async def add_movie(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.post_json("/api/v3/movie", payload)

    async def movie_files(self, movie_id: int) -> list[dict[str, Any]]:
        return await self.get_json("/api/v3/moviefile", movieId=movie_id)

    async def delete_movie_file(self, file_id: int) -> None:
        await self.delete(f"/api/v3/moviefile/{file_id}")

    async def search_movies(self, movie_ids: list[int]) -> dict[str, Any]:
        return await self.command("MoviesSearch", movieIds=movie_ids)


# --------------------------------------------------------------------------
# Mapping
# --------------------------------------------------------------------------


def release_from_arr(app: Literal["sonarr", "radarr", "whisparr"], item: dict[str, Any]) -> ReleaseCandidate:
    """Normalise one `/api/v3/release` item.

    >>> r = release_from_arr("sonarr", {"guid": "g", "indexerId": 3, "title": "Show.S01.1080p",
    ...     "size": 1073741824, "seeders": 12, "quality": {"quality": {"name": "Bluray-1080p",
    ...     "resolution": 1080}}, "rejections": ["Wrong season"], "fullSeason": True,
    ...     "seasonNumber": 1, "languages": [{"name": "English"}], "ageHours": 48})
    >>> (r.quality, r.resolution, r.size_gb, r.full_season, r.languages, r.age_days)
    ('Bluray-1080p', 1080, 1.0, True, ['English'], 2.0)
    """
    quality = (item.get("quality") or {}).get("quality") or {}
    rejections = [
        r if isinstance(r, str) else str(r.get("reason") or r) for r in item.get("rejections") or []
    ]
    mapped = item.get("mappedEpisodeInfo") or []
    age_hours = item.get("ageHours")
    age_days = item.get("age")
    if age_hours is not None:
        age_days = round(float(age_hours) / 24.0, 1)
    return ReleaseCandidate(
        app=app,
        guid=str(item.get("guid")),
        indexer_id=int(item.get("indexerId") or 0),
        indexer=str(item.get("indexer") or ""),
        title=str(item.get("title") or ""),
        size=int(item.get("size") or 0),
        protocol=str(item.get("protocol") or "torrent"),
        seeders=item.get("seeders"),
        leechers=item.get("leechers"),
        age_days=age_days,
        download_url=item.get("downloadUrl"),
        magnet_url=item.get("magnetUrl"),
        info_hash=(item.get("infoHash") or None),
        info_url=item.get("infoUrl"),
        quality=quality.get("name"),
        resolution=quality.get("resolution"),
        languages=[lang.get("name") for lang in item.get("languages") or [] if lang.get("name")],
        release_group=item.get("releaseGroup"),
        custom_formats=[cf.get("name") for cf in item.get("customFormats") or [] if cf.get("name")],
        custom_format_score=int(item.get("customFormatScore") or 0),
        rejections=rejections,
        full_season=bool(item.get("fullSeason")),
        season_number=item.get("mappedSeasonNumber", item.get("seasonNumber")),
        episode_numbers=list(item.get("mappedEpisodeNumbers") or item.get("episodeNumbers") or []),
        episode_ids=[e["id"] for e in mapped if isinstance(e, dict) and "id" in e],
        series_id=item.get("mappedSeriesId") or item.get("seriesId"),
        movie_id=item.get("mappedMovieId") or item.get("movieId"),
        quality_raw=item.get("quality"),
        languages_raw=list(item.get("languages") or []),
    )


class WhisparrClient(RadarrClient):
    """Whisparr v3 (adult) — a Radarr fork; items are movies OR scenes
    (`itemType`), keyed by StashDB/TPDB ids (`foreignId`, `stashId`)."""

    name = "whisparr"
    app = "whisparr"  # type: ignore[assignment]

    async def lookup_scenes(self, term: str) -> list[dict[str, Any]]:
        return await self.get_json("/api/v3/lookup/scene", term=term)

    async def lookup_movies(self, term: str) -> list[dict[str, Any]]:
        return await self.get_json("/api/v3/lookup/movie", term=term)

    async def item_by_stash_id(self, stash_id: str) -> list[dict[str, Any]]:
        return await self.get_json("/api/v3/movie", stashId=stash_id)
