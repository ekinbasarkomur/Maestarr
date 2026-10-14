"""Discovery operations — search titles, details with IMDb ratings, watch
history, taste profile and recommendations."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Literal, Optional

from maestarr.clients.base import ServiceError
from maestarr.clients.history_sources import letterboxd_export
from maestarr.clients.tmdb import tmdb_kind
from maestarr.domain import MediaKind, MediaRef, TasteProfile, WatchEvent
from maestarr.services import Services
from maestarr.taste.profile import DetailsCache, build_profile, merge_history
from maestarr.taste.recommend import RecommendRequest, recommend

logger = logging.getLogger(__name__)

PROFILE_TTL = 6 * 3600


def _cache(svc: Services) -> DetailsCache:
    return DetailsCache(svc.need_tmdb(), svc.memo)


async def library_index(svc: Services) -> tuple[set[tuple[str, int]], dict[str, Any]]:
    """(kind, tmdb id) pairs already in Sonarr/Radarr, plus id lookups."""
    owned: set[tuple[str, int]] = set()
    by_tvdb: dict[int, int] = {}
    by_tmdb_movie: dict[int, int] = {}
    if svc.radarr:
        for m in await svc.radarr.movies():
            if m.get("tmdbId"):
                owned.add(("movie", m["tmdbId"]))
                by_tmdb_movie[m["tmdbId"]] = m["id"]
    if svc.sonarr:
        for s in await svc.sonarr.series():
            if s.get("tmdbId"):
                owned.add(("tv", s["tmdbId"]))
            if s.get("tvdbId"):
                by_tvdb[s["tvdbId"]] = s["id"]
    return owned, {"series_by_tvdb": by_tvdb, "movie_by_tmdb": by_tmdb_movie}


async def watch_history(svc: Services, limit: int = 400) -> list[WatchEvent]:
    sources: list[list[WatchEvent]] = []
    tasks = []
    if svc.jellyfin:
        tasks.append(svc.jellyfin.watch_history(limit))
    if svc.trakt and svc.settings.TRAKT_USERNAME:
        tasks.append(svc.trakt.watched(svc.settings.TRAKT_USERNAME))
    if svc.anilist and svc.settings.ANILIST_USERNAME:
        tasks.append(svc.anilist.user_history(svc.settings.ANILIST_USERNAME))
    for result in await asyncio.gather(*tasks, return_exceptions=True):
        if isinstance(result, Exception):
            logger.warning("history source failed: %s", result)
        else:
            sources.append(result)
    if svc.settings.LETTERBOXD_EXPORT:
        try:
            sources.append(letterboxd_export(svc.settings.LETTERBOXD_EXPORT))
        except OSError as exc:
            logger.warning("letterboxd export unreadable: %s", exc)
    return merge_history(*sources)


async def recent_history(svc: Services, limit: int = 25) -> list[dict[str, Any]]:
    events = await watch_history(svc)
    return [
        {"kind": e.kind, "title": e.title, "year": e.year, "watched": e.watched_at.date().isoformat() if e.watched_at else None,
         "plays": e.play_count, "rating": e.rating, "source": e.source}
        for e in events[:limit]
    ]


async def taste_profile(svc: Services, refresh: bool = False) -> TasteProfile:
    cached = svc.memo.get("taste_profile")
    if cached and not refresh and time.time() - cached[0] < PROFILE_TTL:
        return cached[1]
    history = await watch_history(svc)
    if not history:
        raise ServiceError("maestarr", "no watch history — configure Jellyfin (or Trakt/AniList/Letterboxd)")
    profile = await build_profile(history, _cache(svc))
    svc.memo["taste_profile"] = (time.time(), profile)
    return profile


def profile_summary(p: TasteProfile) -> dict[str, Any]:
    return {
        "history_size": p.history_size,
        "top_genres": p.top("genres", 8),
        "top_themes": p.top("keywords", 15),
        "favourite_people": p.top("people", 10),
        "languages": p.top("languages", 5),
        "decades": p.top("decades", 5),
        "anchor_titles": [f"{s.title} ({s.year})" for s in p.seeds[:10]],
    }


async def _imdb(svc: Services, refs: list[MediaRef]) -> None:
    if not svc.omdb:
        return

    async def one(ref: MediaRef) -> None:
        if not ref.imdb_id:
            return
        try:
            ref.imdb_rating, _ = await svc.omdb.rating(ref.imdb_id)  # type: ignore[union-attr]
        except ServiceError:
            pass

    await asyncio.gather(*(one(r) for r in refs))


def _ref_out(ref: MediaRef) -> dict[str, Any]:
    data = ref.model_dump(exclude_none=True, exclude={"keywords"})
    if ref.overview:
        data["overview"] = ref.overview[:280]
    if ref.keywords:
        data["themes"] = ref.keywords[:8]
    return data


async def search_titles(svc: Services, query: str, kind: MediaKind = "movie", year: Optional[int] = None) -> list[dict[str, Any]]:
    """Search TMDB (or AniList for anime) and mark what is already owned/watched."""
    if kind == "anime" and svc.anilist:
        refs = await svc.anilist.search(query)
    else:
        tmdb = svc.need_tmdb()
        hits = await tmdb.search(tmdb_kind(kind), query, year)
        refs = [await tmdb.to_ref(tmdb_kind(kind), h, anime=kind == "anime") for h in hits[:8]]
    owned, _ = await library_index(svc)
    for r in refs:
        if r.tmdb_id:
            r.in_library = (tmdb_kind(r.kind), r.tmdb_id) in owned
    return [_ref_out(r) for r in refs]


async def title_details(svc: Services, kind: MediaKind, tmdb_id: Optional[int] = None, anilist_id: Optional[int] = None) -> dict[str, Any]:
    if anilist_id and svc.anilist:
        recs = await svc.anilist.recommendations(anilist_id)
        mapped = await svc.anilist.mapped_ids(anilist_id)
        tmdb_id = tmdb_id or mapped.get("tmdb_id")
        if not tmdb_id or not svc.tmdb:
            return {"anilist_id": anilist_id, "ids": mapped, "similar": [r.title for r in recs[:8]]}
    if not tmdb_id:
        raise ServiceError("maestarr", "give a tmdb_id (or anilist_id for anime)")
    tmdb = svc.need_tmdb()
    k = tmdb_kind(kind)
    det = await tmdb.details(k, tmdb_id)
    ref = await tmdb.to_ref(k, det, anime=kind == "anime")
    await _imdb(svc, [ref])
    owned, ids = await library_index(svc)
    ref.in_library = (k, tmdb_id) in owned
    from maestarr.clients.tmdb import credits_people

    out = _ref_out(ref)
    out["people"] = credits_people(det)[:8]
    out["similar"] = [s.get("title") or s.get("name") for s in (det.get("recommendations") or {}).get("results", [])[:6]]
    if k == "tv":
        out["seasons"] = det.get("number_of_seasons")
        out["episodes"] = det.get("number_of_episodes")
        out["status"] = det.get("status")
        if ref.tvdb_id and ref.tvdb_id in ids["series_by_tvdb"]:
            out["series_id"] = ids["series_by_tvdb"][ref.tvdb_id]
    elif tmdb_id in ids["movie_by_tmdb"]:
        out["movie_id"] = ids["movie_by_tmdb"][tmdb_id]
    return out


async def recommendations(
    svc: Services,
    *,
    kind: MediaKind = "movie",
    mood: Optional[str] = None,
    mood_keywords: Optional[list[str]] = None,
    genres: Optional[list[str]] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    language: Optional[str] = None,
    max_runtime: Optional[int] = None,
    min_rating: float = 6.0,
    limit: int = 8,
    include_owned: bool = True,
) -> dict[str, Any]:
    profile = await taste_profile(svc)
    owned, ids = await library_index(svc)
    history = await watch_history(svc)
    cache = _cache(svc)
    watched: set[tuple[str, int]] = set()
    resolved = await asyncio.gather(*(cache.resolve(e) for e in history[:300]))
    for r in resolved:
        if r:
            watched.add(r)
    req = RecommendRequest(
        kind=kind, mood=mood, mood_keywords=mood_keywords or [], genres=genres or [],
        year_from=year_from, year_to=year_to, language=language, max_runtime=max_runtime,
        min_rating=min_rating, limit=limit, include_owned=include_owned,
    )
    recs = await recommend(req, profile, cache, owned=owned, watched=watched)
    await _imdb(svc, [r.item for r in recs])
    rows = []
    for r in recs:
        row = _ref_out(r.item)
        row["match"] = round(r.score * 100)
        row["why"] = r.why
        if r.item.in_library and r.item.kind == "movie" and r.item.tmdb_id in ids["movie_by_tmdb"]:
            row["movie_id"] = ids["movie_by_tmdb"][r.item.tmdb_id]
        rows.append(row)
    return {"based_on": profile_summary(profile)["anchor_titles"][:5], "recommendations": rows}


async def adult_search(svc: Services, query: str, what: Literal["scenes", "performers"] = "scenes") -> list[dict[str, Any]]:
    if not svc.stashdb:
        raise ServiceError("stashdb", "disabled — set STASHDB_ENABLED=true and STASHDB_API_KEY")
    if what == "performers":
        return await svc.stashdb.search_performers(query)
    return await svc.stashdb.search_scenes(query)
