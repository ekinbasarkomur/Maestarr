"""Library operations — what is in Sonarr/Radarr, adding and removing things.

Return values are compact dicts/models shaped for an LLM: ids it can pass back,
human sizes, and nothing it does not need.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Literal, Optional

from maestarr.clients.base import ServiceError
from maestarr.domain import GiB
from maestarr.services import Services


def _gb(size: Any) -> float:
    return round((size or 0) / GiB, 2)


async def search_library(svc: Services, term: str) -> list[dict[str, Any]]:
    """Series and movies already in Sonarr/Radarr whose title contains `term`."""
    needle = term.lower().strip()
    out: list[dict[str, Any]] = []
    if svc.sonarr:
        for s in await svc.sonarr.series():
            titles = [s.get("title", "")] + [a.get("title", "") for a in s.get("alternateTitles") or []]
            if any(needle in t.lower() for t in titles):
                stats = s.get("statistics") or {}
                out.append(
                    {
                        "kind": "anime" if s.get("seriesType") == "anime" else "series",
                        "series_id": s["id"],
                        "title": s["title"],
                        "year": s.get("year"),
                        "tvdb_id": s.get("tvdbId"),
                        "monitored": s.get("monitored"),
                        "episodes_with_files": stats.get("episodeFileCount"),
                        "episodes_total": stats.get("episodeCount"),
                        "size_gb": _gb(stats.get("sizeOnDisk")),
                    }
                )
    for app in (svc.radarr, svc.whisparr):
        if not app:
            continue
        for m in await app.movies():
            if needle in m.get("title", "").lower() or needle in (m.get("originalTitle") or "").lower() \
                    or needle in (m.get("studioTitle") or "").lower():
                out.append(
                    {
                        "kind": "movie" if app.app == "radarr" else f"adult {m.get('itemType', 'movie')}",
                        "app": app.app,
                        "movie_id": m["id"],
                        "title": m["title"],
                        "year": m.get("year"),
                        "tmdb_id": m.get("tmdbId"),
                        "monitored": m.get("monitored"),
                        "has_file": m.get("hasFile"),
                        "size_gb": _gb(m.get("sizeOnDisk")),
                    }
                )
    return out


async def series_details(svc: Services, series_id: int) -> dict[str, Any]:
    """Per-season state of a series: episodes, files, size, missing ones."""
    sonarr = svc.need_sonarr()
    series = await sonarr.series_by_id(series_id)
    episodes = await sonarr.episodes(series_id)
    files = {f["id"]: f for f in await sonarr.episode_files(series_id)}
    seasons: dict[int, dict[str, Any]] = defaultdict(
        lambda: {"episodes": 0, "with_files": 0, "size_gb": 0.0, "missing": [], "qualities": set()}
    )
    for ep in episodes:
        sn = ep["seasonNumber"]
        row = seasons[sn]
        row["episodes"] += 1
        if ep.get("hasFile") and ep.get("episodeFileId") in files:
            f = files[ep["episodeFileId"]]
            row["with_files"] += 1
            row["size_gb"] += (f.get("size") or 0) / GiB
            row["qualities"].add(((f.get("quality") or {}).get("quality") or {}).get("name"))
        elif ep.get("monitored") and sn > 0:
            row["missing"].append(ep["episodeNumber"])
    monitored = {s["seasonNumber"]: s.get("monitored") for s in series.get("seasons", [])}
    return {
        "series_id": series_id,
        "title": series["title"],
        "year": series.get("year"),
        "type": series.get("seriesType"),
        "path": series.get("path"),
        "tvdb_id": series.get("tvdbId"),
        "runtime_minutes": series.get("runtime"),
        "quality_profile_id": series.get("qualityProfileId"),
        "seasons": [
            {
                "season": sn,
                "monitored": monitored.get(sn),
                "episodes": row["episodes"],
                "with_files": row["with_files"],
                "size_gb": round(row["size_gb"], 2),
                "qualities": sorted(q for q in row["qualities"] if q),
                "missing_episodes": row["missing"][:40],
            }
            for sn, row in sorted(seasons.items())
        ],
    }


async def movie_details(svc: Services, movie_id: int, app: str = "radarr") -> dict[str, Any]:
    radarr = svc.need_movie_app(app)
    m = await radarr.movie_by_id(movie_id)
    f = m.get("movieFile") or {}
    return {
        "movie_id": movie_id,
        "title": m["title"],
        "year": m.get("year"),
        "tmdb_id": m.get("tmdbId"),
        "imdb_id": m.get("imdbId"),
        "runtime_minutes": m.get("runtime"),
        "path": m.get("path"),
        "monitored": m.get("monitored"),
        "app": app,
        "item_type": m.get("itemType"),
        "studio": m.get("studioTitle"),
        "has_file": m.get("hasFile"),
        "file": {
            "path": f.get("relativePath"),
            "size_gb": _gb(f.get("size")),
            "quality": ((f.get("quality") or {}).get("quality") or {}).get("name"),
        }
        if f
        else None,
    }


async def queue(svc: Services) -> list[dict[str, Any]]:
    """Everything Sonarr and Radarr are currently downloading or importing."""
    items: list[dict[str, Any]] = []
    for app in (svc.sonarr, svc.radarr, svc.whisparr):
        if not app:
            continue
        seen: set[str] = set()
        for q in await app.queue():
            key = q.get("downloadId") or str(q.get("id"))
            if key in seen:  # a season pack shows once per episode
                continue
            seen.add(key)
            size = q.get("size") or 0
            left = q.get("sizeleft") or 0
            items.append(
                {
                    "app": app.app,
                    "queue_id": q.get("id"),
                    "title": q.get("title"),
                    "status": q.get("status"),
                    "state": q.get("trackedDownloadState"),
                    "progress_pct": round(100 * (1 - left / size), 1) if size else None,
                    "size_gb": _gb(size),
                    "eta": q.get("timeleft"),
                    "download_id": q.get("downloadId"),
                    "problems": [m.get("title") for m in q.get("statusMessages") or []][:3],
                }
            )
    return items


async def disk_usage(svc: Services) -> list[dict[str, Any]]:
    disks: dict[str, dict[str, Any]] = {}
    for app in (svc.sonarr, svc.radarr, svc.whisparr):
        if not app:
            continue
        try:
            for d in await app.disk_space():
                disks[d["path"]] = {
                    "path": d["path"],
                    "free_gb": _gb(d.get("freeSpace")),
                    "total_gb": _gb(d.get("totalSpace")),
                }
        except ServiceError:
            continue
    return sorted(disks.values(), key=lambda d: -d["total_gb"])


async def lookup(svc: Services, term: str, kind: Literal["series", "anime", "movie"]) -> list[dict[str, Any]]:
    """Find a title to ADD (Sonarr/Radarr lookup through their metadata)."""
    if kind == "movie":
        results = await svc.need_radarr().lookup(term)
        return [
            {"title": r["title"], "year": r.get("year"), "tmdb_id": r.get("tmdbId"), "in_library": bool(r.get("id")),
             "overview": (r.get("overview") or "")[:200]}
            for r in results[:8]
        ]
    results = await svc.need_sonarr().lookup(term)
    return [
        {"title": r["title"], "year": r.get("year"), "tvdb_id": r.get("tvdbId"), "in_library": bool(r.get("id")),
         "seasons": len([s for s in r.get("seasons", []) if s["seasonNumber"] > 0]), "network": r.get("network"),
         "overview": (r.get("overview") or "")[:200]}
        for r in results[:8]
    ]


async def _defaults(app: Any, quality_profile: Optional[str], root_folder: Optional[str]) -> tuple[int, str]:
    profiles = await app.quality_profiles()
    roots = await app.root_folders()
    if not profiles or not roots:
        raise ServiceError(app.name, "no quality profile or root folder configured")
    profile = next((p for p in profiles if quality_profile and p["name"].lower() == quality_profile.lower()), profiles[0])
    root = next((r for r in roots if root_folder and r["path"].rstrip("/") == root_folder.rstrip("/")), roots[0])
    return profile["id"], root["path"]


async def add_series(
    svc: Services,
    tvdb_id: int,
    *,
    anime: bool = False,
    monitor: str = "all",
    search_now: bool = False,
    quality_profile: Optional[str] = None,
    root_folder: Optional[str] = None,
) -> dict[str, Any]:
    sonarr = svc.need_sonarr()
    found = await sonarr.lookup(f"tvdb:{tvdb_id}")
    if not found:
        raise ServiceError("sonarr", f"no series with tvdb id {tvdb_id}")
    item = found[0]
    if item.get("id"):
        return {"already_in_library": True, "series_id": item["id"], "title": item["title"]}
    s = svc.settings
    if anime:
        quality_profile = quality_profile or s.SONARR_ANIME_QUALITY_PROFILE or s.SONARR_QUALITY_PROFILE
        root_folder = root_folder or s.SONARR_ANIME_ROOT_FOLDER
    else:
        quality_profile = quality_profile or s.SONARR_QUALITY_PROFILE
        root_folder = root_folder or s.SONARR_ROOT_FOLDER
    profile_id, root = await _defaults(sonarr, quality_profile, root_folder)
    if anime and not root_folder:
        for r in await sonarr.root_folders():
            if "anime" in r["path"].lower():
                root = r["path"]
    payload = {
        **item,
        "qualityProfileId": profile_id,
        "rootFolderPath": root,
        "monitored": monitor != "none",
        "seasonFolder": True,
        "seriesType": "anime" if anime else "standard",
        "addOptions": {"monitor": monitor, "searchForMissingEpisodes": search_now, "searchForCutoffUnmetEpisodes": False},
    }
    created = await sonarr.add_series(payload)
    return {"series_id": created["id"], "title": created["title"], "path": created.get("path"), "searching": search_now}


async def add_movie(
    svc: Services,
    tmdb_id: int,
    *,
    search_now: bool = False,
    quality_profile: Optional[str] = None,
    root_folder: Optional[str] = None,
) -> dict[str, Any]:
    radarr = svc.need_radarr()
    item = await radarr.lookup_tmdb(tmdb_id)
    if item.get("id"):
        return {"already_in_library": True, "movie_id": item["id"], "title": item["title"]}
    profile_id, root = await _defaults(
        radarr, quality_profile or svc.settings.RADARR_QUALITY_PROFILE, root_folder or svc.settings.RADARR_ROOT_FOLDER
    )
    payload = {
        **item,
        "qualityProfileId": profile_id,
        "rootFolderPath": root,
        "monitored": True,
        "minimumAvailability": "released",
        "addOptions": {"searchForMovie": search_now, "monitor": "movieOnly", "addMethod": "manual"},
    }
    created = await radarr.add_movie(payload)
    return {"movie_id": created["id"], "title": created["title"], "path": created.get("path"), "searching": search_now}


async def delete_series_files(
    svc: Services,
    series_id: int,
    *,
    seasons: Optional[list[int]] = None,
    episodes: Optional[list[int]] = None,
    unmonitor: bool = False,
) -> dict[str, Any]:
    """Delete episode files (whole seasons or single episodes of one season).

    Files imported by hardlink still occupy space until the matching torrent is
    removed with its data — the result lists the torrents that hold them.
    """
    sonarr = svc.need_sonarr()
    eps = await sonarr.episodes(series_id)
    chosen = [
        e for e in eps
        if e.get("hasFile")
        and (seasons is None or e["seasonNumber"] in seasons)
        and (episodes is None or e["episodeNumber"] in episodes)
    ]
    if seasons is None and episodes is None:
        raise ServiceError("sonarr", "refusing to delete a whole series without explicit seasons or episodes")
    file_ids = sorted({e["episodeFileId"] for e in chosen if e.get("episodeFileId")})
    files = {f["id"]: f for f in await sonarr.episode_files(series_id)}
    freed = sum((files.get(i) or {}).get("size", 0) for i in file_ids)
    if file_ids:
        await sonarr.delete_episode_files(file_ids)
    if unmonitor and chosen:
        await sonarr.set_episodes_monitored([e["id"] for e in chosen], False)
    holders = await torrents_holding(svc, [(files.get(i) or {}).get("relativePath", "") for i in file_ids])
    return {
        "deleted_files": len(file_ids),
        "library_gb": _gb(freed),
        "unmonitored": unmonitor,
        "torrents_still_holding_data": holders,
        "note": "space is only freed once those torrents are removed with their data" if holders else None,
    }


async def delete_movie_file(svc: Services, movie_id: int, *, unmonitor: bool = False, app: str = "radarr") -> dict[str, Any]:
    radarr = svc.need_movie_app(app)
    movie = await radarr.movie_by_id(movie_id)
    f = movie.get("movieFile")
    if not f:
        return {"deleted": False, "reason": "movie has no file"}
    await radarr.delete_movie_file(f["id"])
    if unmonitor:
        movie["monitored"] = False
        await radarr.put_json(f"/api/v3/movie/{movie_id}", movie)
    holders = await torrents_holding(svc, [f.get("relativePath", "")])
    return {"deleted": True, "library_gb": _gb(f.get("size")), "torrents_still_holding_data": holders}


async def torrents_holding(svc: Services, relative_paths: list[str]) -> list[dict[str, Any]]:
    """qBittorrent torrents whose content matches any of these file names."""
    if not svc.qbittorrent or not relative_paths:
        return []
    import asyncio

    qbit = svc.qbittorrent
    names = {p.rsplit("/", 1)[-1].lower() for p in relative_paths if p}
    stems = {n.rsplit(".", 1)[0] for n in names}
    torrents = await qbit.torrents()
    sem = asyncio.Semaphore(6)

    async def holds(t: dict[str, Any]) -> bool:
        tname = (t.get("name") or "").lower()
        if any(s and (s in tname or tname in s) for s in stems):
            return True
        async with sem:
            try:
                files = await qbit.files(t["hash"])
            except ServiceError:
                return False
        return any(f["name"].rsplit("/", 1)[-1].lower() in names for f in files)

    flags = await asyncio.gather(*(holds(t) for t in torrents))
    return [
        {"hash": t["hash"], "name": t["name"], "size_gb": _gb(t.get("size")), "state": t.get("state")}
        for t, held in zip(torrents, flags)
        if held
    ][:20]


async def trigger_search(
    svc: Services, *, series_id: Optional[int] = None, season: Optional[int] = None, movie_id: Optional[int] = None,
    app: str = "radarr",
) -> dict[str, Any]:
    """Let Sonarr/Radarr/Whisparr search and grab automatically by their own rules."""
    if movie_id is not None:
        cmd = await svc.need_movie_app(app).search_movies([movie_id])
    elif series_id is not None and season is not None:
        cmd = await svc.need_sonarr().search_season(series_id, season)
    elif series_id is not None:
        cmd = await svc.need_sonarr().search_series(series_id)
    else:
        raise ServiceError("maestarr", "give a series_id (optionally with season) or a movie_id")
    return {"command_id": cmd.get("id"), "status": cmd.get("status")}


async def wanted_missing(svc: Services) -> list[dict[str, Any]]:
    out = []
    if svc.sonarr:
        for r in await svc.sonarr.wanted_missing():
            series = r.get("series") or {}
            out.append(
                {"series": series.get("title"), "series_id": r.get("seriesId"), "season": r.get("seasonNumber"),
                 "episode": r.get("episodeNumber"), "title": r.get("title"), "aired": (r.get("airDateUtc") or "")[:10]}
            )
    return out[:60]


def _unwrap(result: dict[str, Any]) -> dict[str, Any]:
    """Whisparr v3 wraps lookup hits as {foreignId, movie: {...}, id: <rank>};
    the rank is not a library id. Return the movie itself.

    >>> _unwrap({"foreignId": "f", "id": 1, "movie": {"title": "T", "foreignId": "f"}})
    {'title': 'T', 'foreignId': 'f'}
    >>> _unwrap({"title": "Old shape", "id": 7})
    {'title': 'Old shape', 'id': 7}
    """
    inner = result.get("movie")
    return dict(inner) if isinstance(inner, dict) else dict(result)


async def _whisparr_library_id(whisparr: Any, foreign_id: str) -> Optional[int]:
    """The Whisparr item id of a scene/movie already in the library, if any."""
    found = await whisparr.item_by_stash_id(foreign_id)
    if not found:
        found = [m for m in await whisparr.movies() if str(m.get("foreignId")) == str(foreign_id)]
    return int(found[0]["id"]) if found else None


async def whisparr_lookup(svc: Services, term: str, item_type: Literal["scene", "movie"] = "scene") -> list[dict[str, Any]]:
    """Find an adult scene or movie to ADD to Whisparr (StashDB ids work as the term)."""
    whisparr = svc.need_whisparr()
    results = await (whisparr.lookup_scenes(term) if item_type == "scene" else whisparr.lookup_movies(term))
    library = {str(m.get("foreignId")): m["id"] for m in await whisparr.movies()}
    out = []
    for raw in results[:10]:
        r = _unwrap(raw)
        foreign_id = str(r.get("foreignId") or raw.get("foreignId") or "")
        movie_id = library.get(foreign_id)
        out.append({
            "title": r.get("title"),
            "year": r.get("year"),
            "date": (r.get("releaseDate") or "")[:10] or None,
            "studio": r.get("studioTitle"),
            "foreign_id": foreign_id,
            "item_type": r.get("itemType", item_type),
            "in_library": movie_id is not None,
            "movie_id": movie_id,
            "minutes": r.get("runtime"),
        })
    return out


async def whisparr_add(
    svc: Services,
    foreign_id: str,
    *,
    item_type: Literal["scene", "movie"] = "scene",
    search_now: bool = False,
    quality_profile: Optional[str] = None,
    root_folder: Optional[str] = None,
) -> dict[str, Any]:
    whisparr = svc.need_whisparr()
    lookup = await (whisparr.lookup_scenes(foreign_id) if item_type == "scene" else whisparr.lookup_movies(foreign_id))
    raw = next((r for r in lookup if str(r.get("foreignId")) == str(foreign_id)), lookup[0] if lookup else None)
    if raw is None:
        raise ServiceError("whisparr", f"nothing found for {foreign_id}")
    item = _unwrap(raw)
    item.pop("id", None)
    existing = await _whisparr_library_id(whisparr, str(item.get("foreignId") or foreign_id))
    if existing is not None:
        return {"already_in_library": True, "movie_id": existing, "title": item.get("title"), "app": "whisparr"}
    profile_id, root = await _defaults(
        whisparr,
        quality_profile or svc.settings.WHISPARR_QUALITY_PROFILE,
        root_folder or svc.settings.WHISPARR_ROOT_FOLDER,
    )
    payload = {
        **item,
        "qualityProfileId": profile_id,
        "rootFolderPath": root,
        "monitored": True,
        "addOptions": {"searchForMovie": search_now, "monitor": "movieOnly", "addMethod": "manual"},
    }
    created = await whisparr.add_movie(payload)
    return {"movie_id": created["id"], "title": created.get("title"), "app": "whisparr", "searching": search_now}


async def item_title(svc: Services, app: str, item_id: int) -> str:
    """'Title (year)' of a library item, for approval cards."""
    try:
        if app == "sonarr":
            item = await svc.need_sonarr().series_by_id(item_id)
        else:
            item = await svc.need_movie_app(app).movie_by_id(item_id)
    except ServiceError:
        return f"{app} item {item_id}"
    return f"{item.get('title')}" + (f" ({item['year']})" if item.get("year") else "")


async def set_monitored(
    svc: Services,
    *,
    app: str,
    item_id: int,
    monitored: bool,
    season: Optional[int] = None,
    episodes: Optional[list[int]] = None,
) -> dict[str, Any]:
    """Turn monitoring on or off without touching any file.

    Movies/scenes as a whole; series as a whole, one season, or episodes of a season.
    """
    if app in ("radarr", "whisparr"):
        movies = svc.need_movie_app(app)
        await movies.put_json("/api/v3/movie/editor", {"movieIds": [item_id], "monitored": monitored})
        return {"app": app, "movie_id": item_id, "monitored": monitored, "title": await item_title(svc, app, item_id)}
    sonarr = svc.need_sonarr()
    if episodes:
        if season is None:
            raise ServiceError("maestarr", "give the season for these episodes")
        eps = await sonarr.episodes(item_id)
        ids = [e["id"] for e in eps if e["seasonNumber"] == season and e["episodeNumber"] in episodes]
        if not ids:
            raise ServiceError("sonarr", f"none of those episodes exist in season {season}")
        await sonarr.set_episodes_monitored(ids, monitored)
        return {"app": "sonarr", "series_id": item_id, "season": season, "episodes": episodes, "monitored": monitored}
    if season is not None:
        series = await sonarr.series_by_id(item_id)
        found = False
        for s in series.get("seasons") or []:
            if s.get("seasonNumber") == season:
                s["monitored"] = monitored
                found = True
        if not found:
            raise ServiceError("sonarr", f"season {season} not found")
        await sonarr.put_json(f"/api/v3/series/{item_id}", series)
        return {"app": "sonarr", "series_id": item_id, "season": season, "monitored": monitored, "title": series.get("title")}
    await sonarr.put_json("/api/v3/series/editor", {"seriesIds": [item_id], "monitored": monitored})
    return {"app": "sonarr", "series_id": item_id, "monitored": monitored, "title": await item_title(svc, "sonarr", item_id)}


async def remove_from_library(
    svc: Services, *, app: str, item_id: int, delete_files: bool = False, exclude: bool = False
) -> dict[str, Any]:
    """Remove a series, movie or scene from its app. Files stay unless asked;
    `exclude` keeps import lists from adding it back."""
    title = await item_title(svc, app, item_id)
    if app == "sonarr":
        await svc.need_sonarr().delete(
            f"/api/v3/series/{item_id}", deleteFiles=str(delete_files).lower(), addImportListExclusion=str(exclude).lower()
        )
    else:
        await svc.need_movie_app(app).delete(
            f"/api/v3/movie/{item_id}", deleteFiles=str(delete_files).lower(), addImportExclusion=str(exclude).lower()
        )
    return {"removed": True, "app": app, "title": title, "files_deleted": delete_files, "excluded": exclude}
