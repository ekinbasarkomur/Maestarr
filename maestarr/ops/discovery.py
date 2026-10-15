"""Discovery operations — search titles, details with IMDb ratings, watch
history, taste profile and recommendations."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import Counter
from datetime import datetime
from typing import Any, Literal, Optional

from maestarr.cache import CacheStore, cached, store_for
from maestarr.clients.base import ServiceError
from maestarr.clients.history_sources import letterboxd_export
from maestarr.clients.tmdb import tmdb_kind
from maestarr.domain import MediaKind, MediaRef, TasteProfile, WatchEvent
from maestarr.services import Services
from maestarr.taste.feedback import FeedbackState, FeedbackStore
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


HISTORY_TTL = 15 * 60


def _parse_added(value: Any) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")) if value else None
    except ValueError:
        return None


async def library_history(svc: Services, limit: int = 300) -> list[WatchEvent]:
    """What the user chose to keep, as a weak stand-in for watch history.

    Used only when no real history exists (a fresh Jellyfin, no Trakt), so
    recommendations still have something to start from.
    """
    events: list[WatchEvent] = []
    if svc.radarr:
        for m in await svc.radarr.movies():
            if m.get("hasFile") and m.get("title"):
                events.append(WatchEvent(
                    kind="movie", title=m["title"], year=m.get("year"), tmdb_id=m.get("tmdbId"),
                    imdb_id=m.get("imdbId"), watched_at=_parse_added(m.get("added")), source="library",
                ))
    if svc.sonarr:
        for s in await svc.sonarr.series():
            if (s.get("statistics") or {}).get("episodeFileCount") and s.get("title"):
                events.append(WatchEvent(
                    kind="anime" if s.get("seriesType") == "anime" else "series", title=s["title"],
                    year=s.get("year"), tmdb_id=s.get("tmdbId"), tvdb_id=s.get("tvdbId"),
                    imdb_id=s.get("imdbId"), watched_at=_parse_added(s.get("added")), source="library",
                ))
    events.sort(key=lambda e: e.watched_at.timestamp() if e.watched_at else 0.0, reverse=True)
    return events[:limit]


def cache_store(svc: Services) -> CacheStore:
    return store_for(svc.settings.database_path)


def data_age(svc: Services) -> float:
    """How old watch history, libraries and the taste profile may get."""
    return max(1, svc.settings.MAESTARR_DATA_REFRESH_HOURS) * 3600.0


def picks_age(svc: Services) -> Optional[float]:
    """How long suggestion shelves stay as they are (None: only refreshed by hand)."""
    s = svc.settings
    return max(1, s.MAESTARR_PICKS_REFRESH_HOURS) * 3600.0 if s.MAESTARR_PICKS_REFRESH else None


def _events_out(events: list[WatchEvent]) -> list[dict[str, Any]]:
    return [e.model_dump(mode="json") for e in events]


def _events_in(raw: list[dict[str, Any]]) -> list[WatchEvent]:
    return [WatchEvent.model_validate(e) for e in raw]


async def watch_history(svc: Services, limit: int = 400) -> list[WatchEvent]:
    """Merged history from every source — cached, because Jellyfin can take a minute."""

    async def build() -> list[WatchEvent]:
        history = await _collect_history(svc, limit)
        return history or await library_history(svc)

    events = await cached(cache_store(svc), "data:watch_history", max_age=data_age(svc), build=build,
                          encode=_events_out, decode=_events_in)
    return list(events)


async def _collect_history(svc: Services, limit: int) -> list[WatchEvent]:
    sources: list[list[WatchEvent]] = []
    tasks = []
    if svc.jellyfin:
        tasks.append(svc.jellyfin.watch_history(limit))
    if svc.trakt and svc.settings.TRAKT_USERNAME:
        tasks.append(svc.trakt.watched(svc.settings.TRAKT_USERNAME))
    if svc.anilist and svc.settings.ANILIST_USERNAME:
        tasks.append(svc.anilist.user_history(svc.settings.ANILIST_USERNAME))
    for result in await asyncio.gather(*tasks, return_exceptions=True):
        if isinstance(result, BaseException):
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


def feedback_store(svc: Services) -> FeedbackStore:
    store = svc.memo.get("feedback_store")
    if store is None:
        store = svc.memo["feedback_store"] = FeedbackStore(svc.settings.database_path)
    return store


async def taste_events(svc: Services) -> list[WatchEvent]:
    """Everything that says something about taste: what was watched (and rated),
    plus what was added to Sonarr/Radarr — the latter at a lower weight."""
    async def build() -> list[WatchEvent]:
        watched = await watch_history(svc)
        real = [e for e in watched if e.source != "library"]
        interest = await interest_events(svc)
        library = await library_history(svc) if (svc.sonarr or svc.radarr) else []
        return merge_history(real, interest, library)

    events = await cached(cache_store(svc), "data:taste_events", max_age=data_age(svc), build=build,
                          encode=_events_out, decode=_events_in)
    return list(events)


async def interest_events(svc: Services) -> list[WatchEvent]:
    """Favourites (Jellyfin, AniList), requests (Seerr) and watchlists (Trakt, AniList)."""
    tasks = []
    if svc.jellyfin:
        tasks.append(svc.jellyfin.favorites())
    if svc.seerr:
        tasks.append(svc.seerr.requests())
    if svc.trakt and svc.settings.TRAKT_USERNAME:
        tasks.append(svc.trakt.watchlist_events(svc.settings.TRAKT_USERNAME))
    if svc.anilist and svc.settings.ANILIST_USERNAME:
        tasks.append(svc.anilist.user_interest(svc.settings.ANILIST_USERNAME))
    events: list[WatchEvent] = []
    for result in await asyncio.gather(*tasks, return_exceptions=True):
        if isinstance(result, BaseException):
            logger.warning("interest source failed: %s", result)
        else:
            events += result
    return events


async def taste_profile(svc: Services, refresh: bool = False) -> TasteProfile:
    async def build() -> TasteProfile:
        history = await taste_events(svc)
        if not history:
            raise ServiceError("maestarr", "no watch history and an empty library — watch something in Jellyfin or connect Trakt/AniList")
        return await build_profile(history, _cache(svc))

    store = cache_store(svc)
    if refresh:
        await store.drop("data:taste_profile")
    base: TasteProfile = await cached(
        store, "data:taste_profile", max_age=data_age(svc), build=build,
        encode=lambda p: p.model_dump(mode="json"), decode=TasteProfile.model_validate,
    )
    # Reactions apply at once, on top of the cached profile.
    profile = base.model_copy(deep=True)
    apply_feedback(profile, await feedback_store(svc).state())
    return profile


def apply_feedback(profile: TasteProfile, state: FeedbackState) -> None:
    """Titles the user opened or searched pull their themes up; "not for me"
    titles push theirs down.

    >>> p = TasteProfile(keywords={"heist": 0.4}, genres={"Crime": 1.0})
    >>> apply_feedback(p, FeedbackState(liked=[{"keywords": ["heist", "twist"], "genres": ["Crime"]}],
    ...                                 disliked=[{"keywords": ["gore"], "genres": ["Horror"]}]))
    >>> p.keywords["heist"], p.keywords["twist"], p.avoid
    (0.9, 0.5, {'gore': 1.0, 'Horror': 0.3})
    """
    for item in state.liked:
        for k in item.get("keywords") or []:
            profile.keywords[k] = round(profile.keywords.get(k, 0.0) + 0.5, 3)
        for g in item.get("genres") or []:
            profile.genres[g] = round(profile.genres.get(g, 0.0) + 0.25, 3)
    for item in state.disliked:
        for k in item.get("keywords") or []:
            profile.avoid[k] = 1.0
        for g in item.get("genres") or []:
            profile.avoid.setdefault(g, 0.3)


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
    tags: Optional[list[str]] = None,
) -> dict[str, Any]:
    svc.need_tmdb()  # fail fast: reading history can take a minute on a busy Jellyfin
    profile = await taste_profile(svc)
    owned, ids = await library_index(svc)
    watched = await watched_set(svc)
    cache = _cache(svc)
    state = await feedback_store(svc).state()
    req = RecommendRequest(
        kind=kind, mood=mood, mood_keywords=mood_keywords or [], genres=genres or [],
        year_from=year_from, year_to=year_to, language=language, max_runtime=max_runtime,
        min_rating=min_rating, limit=limit, include_owned=include_owned, tags=tags or [],
    )
    recs = await recommend(req, profile, cache, owned=owned, watched=watched, hidden=state.hidden)
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


async def watched_set(svc: Services) -> set[tuple[str, int]]:
    """(tmdb kind, tmdb id) of everything actually watched (not merely owned)."""
    async def build() -> set[tuple[str, int]]:
        history = [e for e in await watch_history(svc) if e.source != "library"]
        cache = _cache(svc)
        resolved = await asyncio.gather(*(cache.resolve(e) for e in history[:300]))
        return {pair for pair in resolved if pair}

    return set(await cached(
        cache_store(svc), "data:watched_set", max_age=data_age(svc), build=build,
        encode=lambda v: sorted([k, i] for k, i in v), decode=lambda raw: {(k, int(i)) for k, i in raw},
    ))


async def record_impressions(svc: Services, items: list[dict[str, Any]]) -> None:
    """Count these suggestions as shown (for spacing out the ones that are ignored)."""
    rows = [(tmdb_kind(i.get("kind", "movie")), int(i["tmdb_id"]), str(i.get("title") or ""))
            for i in items if i.get("tmdb_id") and i.get("kind") != "scene"]
    if rows:
        try:
            await feedback_store(svc).shown(rows)
        except Exception:  # noqa: BLE001 — bookkeeping must never break a page
            logger.exception("could not record impressions")


async def react(svc: Services, kind: str, tmdb_id: int, action: str, title: Optional[str] = None) -> dict[str, Any]:
    """The user opened, searched, added or turned down a suggestion."""
    genres: Optional[list[str]] = None
    keywords: Optional[list[str]] = None
    k = tmdb_kind(kind)  # type: ignore[arg-type]
    if svc.tmdb:
        det = await _cache(svc).details(k, tmdb_id)
        if det:
            ref = await svc.tmdb.to_ref(k, det)
            genres, keywords, title = ref.genres, ref.keywords[:20], title or ref.title
    await feedback_store(svc).react(k, tmdb_id, action, title=title, genres=genres, keywords=keywords)  # type: ignore[arg-type]
    return {"ok": True, "kind": k, "tmdb_id": tmdb_id, "action": action}


async def adult_search(svc: Services, query: str, what: Literal["scenes", "performers"] = "scenes") -> list[dict[str, Any]]:
    if not svc.settings.MAESTARR_ADULT_CONTENT:
        raise ServiceError("stashdb", "adult content is switched off (Settings → Discovery)")
    if not svc.stashdb:
        raise ServiceError("stashdb", "disabled — set STASHDB_ENABLED=true and STASHDB_API_KEY")
    if what == "performers":
        return await svc.stashdb.search_performers(query)
    return await svc.stashdb.search_scenes(query)


def _adult_gate(svc: Services) -> None:
    if not svc.settings.MAESTARR_ADULT_CONTENT:
        raise ServiceError("stashdb", "adult content is switched off (Settings → Discovery)")
    if not svc.stashdb:
        raise ServiceError("stashdb", "StashDB is not set up — enable it and add an API key under Settings → Discovery")


async def adult_picks(svc: Services, query: Optional[str] = None, limit: int = 12) -> dict[str, Any]:
    """Adult scenes for the Discover page and the agent.

    With a query: StashDB search. Without one: new scenes from the studios and
    performers the Whisparr library holds most of (StashDB trending when the
    library is empty). Scenes already in Whisparr are marked or left out.
    """
    _adult_gate(svc)
    stash = svc.stashdb
    assert stash is not None
    memo_key = f"adult_picks:{(query or '').strip().lower()}:{limit}"
    cached = svc.memo.get(memo_key)
    if cached and time.time() - cached[0] < ADULT_TTL:
        return dict(cached[1])
    result = await _adult_picks(svc, stash, query, limit)
    svc.memo[memo_key] = (time.time(), result)
    return result


ADULT_TTL = 10 * 60


async def _adult_picks(svc: Services, stash: Any, query: Optional[str], limit: int) -> dict[str, Any]:
    library = await svc.whisparr.movies() if svc.whisparr else []
    owned = {str(m.get("stashId") or m.get("foreignId")) for m in library}
    studio_count: Counter[str] = Counter()
    studio_name: dict[str, str] = {}
    performer_count: Counter[str] = Counter()
    performer_name: dict[str, str] = {}
    for m in library:
        if m.get("studioForeignId"):
            studio_count[m["studioForeignId"]] += 1
            studio_name[m["studioForeignId"]] = m.get("studioTitle") or "?"
        for pid, name in zip(m.get("performerForeignIds") or [], m.get("performerNames") or []):
            performer_count[pid] += 1
            performer_name[pid] = name

    based_on: list[str] = []
    if query:
        scenes = await stash.search_scenes(query, limit=limit * 2)
        reasons = {s["id"]: [f"Matches “{query}”"] for s in scenes}
    elif studio_count or performer_count:
        studios = [sid for sid, _ in studio_count.most_common(3)]
        # Libraries are full of the same few male performers; follow the women first.
        top = [pid for pid, n in performer_count.most_common(60) if n >= 2]
        genders = await _genders(svc, stash, top)
        women = [p for p in top if genders.get(p) == "FEMALE"]
        performers = women[:6] if len(women) >= 3 else (women + [p for p in top if p not in women])[:6]
        based_on = [studio_name[s] for s in studios] + [performer_name[p] for p in performers[:4]]
        # One query per performer, interleaved, so the most prolific one does not fill the page.
        batches = await asyncio.gather(
            stash.query_scenes(studios=studios, per_page=40) if studios else _none(),
            *(stash.query_scenes(performers=[p], per_page=12) for p in performers),
        )
        scenes = [s for pair in _interleave(*batches) for s in pair]
        reasons = {}
        for s in scenes:
            why = []
            if s.get("studio_id") in studio_count:
                why.append(f"From {s['studio']} — {studio_count[s['studio_id']]} of their scenes are in your library")
            liked = [p for p in s.get("performer_ids", []) if p in performers]
            if liked:
                n = performer_count[liked[0]]
                why.append(f"With {performer_name[liked[0]]}, who is in {n} of your scenes")
            reasons[s["id"]] = why or ["Similar to your library"]
    else:
        scenes = await stash.query_scenes(sort="TRENDING", per_page=limit * 2)
        reasons = {s["id"]: ["Trending on StashDB this week"] for s in scenes}

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for s in scenes:
        if s["id"] in seen:
            continue
        seen.add(s["id"])
        in_library = s["id"] in owned
        if in_library and not query:
            continue
        out.append({**s, "kind": "scene", "stash_id": s["id"], "why": reasons.get(s["id"], []), "in_library": in_library})
        if len(out) >= limit:
            break
    return {"based_on": based_on, "scenes": out}


async def _genders(svc: Services, stash: Any, ids: list[str]) -> dict[str, str]:
    known: dict[str, str] = svc.memo.setdefault("performer_genders", {})
    missing = [i for i in ids if i not in known]
    if missing:
        try:
            known.update(await stash.performer_genders(missing))
        except ServiceError as exc:
            logger.warning("performer genders unavailable: %s", exc)
    return known


async def _none() -> list[dict[str, Any]]:
    return []


def _interleave(*lists: list[Any]) -> list[tuple[Any, ...]]:
    """Alternate between result lists so one source does not crowd out the other.

    >>> _interleave([1, 2, 3], ["a"])
    [(1,), ('a',), (2,), (3,)]
    """
    out: list[tuple[Any, ...]] = []
    for i in range(max((len(x) for x in lists), default=0)):
        for x in lists:
            if i < len(x):
                out.append((x[i],))
    return out
