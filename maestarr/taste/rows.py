"""Rows of suggestions for the home page and Discover, like a streaming app.

Each row is one idea built from the user's taste: top picks per kind, "because
you watched X", more with a favourite person, a favourite theme, and what has
been waiting unwatched in the library. Titles already watched, already on
another row, or not due yet (spaced out after being ignored) are left out.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Optional

from maestarr.cache import cached
from maestarr.clients.base import ServiceError
from maestarr.clients.tmdb import tmdb_kind
from maestarr.domain import MediaKind, MediaRef
from maestarr.ops import discovery
from maestarr.services import Services
from maestarr.taste.recommend import taste_score

logger = logging.getLogger(__name__)

UNWATCHED_AFTER_DAYS = 21
GENERIC_TAGS = {"based on novel or book", "based on comic", "duringcreditsstinger", "aftercreditsstinger",
                "woman director", "sequel", "remake", "anime", "live action remake", "biography"}


def _row(row_id: str, title: str, items: list[dict[str, Any]], subtitle: Optional[str] = None) -> Optional[dict[str, Any]]:
    return {"id": row_id, "title": title, "subtitle": subtitle, "items": items} if len(items) >= 3 else None


async def build_rows(svc: Services, *, refresh: bool = False) -> dict[str, Any]:
    """The shelves, cached for the picks refresh interval; titles the user has since
    turned down (or that are not due) are filtered out at read time."""
    svc.need_tmdb()
    store = discovery.cache_store(svc)
    if refresh:
        await store.drop("picks:rows")
    out = await cached(store, "picks:rows", max_age=discovery.picks_age(svc), build=lambda: _build_rows(svc))
    hidden = (await discovery.feedback_store(svc).state()).hidden
    rows = []
    for row in out["rows"]:
        items = [i for i in row["items"] if not _hidden(i, hidden)]
        if len(items) >= 3:
            rows.append({**row, "items": items})
    return {**out, "rows": rows}


def _hidden(item: dict[str, Any], hidden: set[tuple[str, int]]) -> bool:
    tmdb_id = item.get("tmdb_id")
    return bool(tmdb_id) and (tmdb_kind(item.get("kind", "movie")), int(tmdb_id)) in hidden  # type: ignore[arg-type]


async def _build_rows(svc: Services) -> dict[str, Any]:
    profile = await discovery.taste_profile(svc)
    state = await discovery.feedback_store(svc).state()
    watched = await discovery.watched_set(svc)
    owned, _ = await discovery.library_index(svc)
    cache = discovery._cache(svc)
    tmdb = cache.tmdb
    used: set[tuple[str, int]] = set()

    def keep(kind: str, item: dict[str, Any]) -> bool:
        key = (tmdb_kind(kind), item.get("tmdb_id") or 0)  # type: ignore[arg-type]
        if not item.get("tmdb_id") or key in used or key in watched or key in state.hidden:
            return False
        used.add(key)
        return True

    async def refs_from(kind: MediaKind, raw: list[dict[str, Any]], why: str, limit: int = 14) -> list[dict[str, Any]]:
        k = tmdb_kind(kind)
        refs = await asyncio.gather(*(tmdb.to_ref(k, r, anime=kind == "anime") for r in raw[:30]))
        scored = sorted(refs, key=lambda r: -taste_score(r, [], profile)[0])
        out = []
        for ref in scored:
            row = discovery._ref_out(ref)
            row["why"] = [why]
            row["in_library"] = (k, ref.tmdb_id) in owned
            if keep(kind, row):
                out.append(row)
            if len(out) >= limit:
                break
        return out

    async def picks(kind: MediaKind) -> list[dict[str, Any]]:
        try:
            data = await discovery.recommendations(svc, kind=kind, limit=14)
        except ServiceError as exc:
            logger.info("no %s picks: %s", kind, exc)
            return []
        return [r for r in data["recommendations"] if keep(kind, r)]

    async def because(seed: MediaRef) -> Optional[dict[str, Any]]:
        if not seed.tmdb_id:
            return None
        kind: MediaKind = "movie" if seed.kind == "movie" else "series"
        det = await cache.details(tmdb_kind(kind), seed.tmdb_id)
        raw = ((det or {}).get("recommendations") or {}).get("results") or []
        items = await refs_from(kind, raw, f"because you watched {seed.title}")
        return _row(f"because-{seed.tmdb_id}", f"Because you watched {seed.title}", items)

    async def person_row(name: str) -> Optional[dict[str, Any]]:
        hits = await tmdb.search_people(name)
        if not hits:
            return None
        credits = await tmdb.person_credits(hits[0]["id"])
        raw = sorted(
            [c for c in (credits.get("cast") or []) + (credits.get("crew") or [])
             if c.get("media_type") in ("movie", "tv") and (c.get("vote_count") or 0) >= 50],
            key=lambda c: -(c.get("popularity") or 0),
        )
        movies = [c for c in raw if c.get("media_type") == "movie"]
        items = await refs_from("movie", movies, f"with {hits[0]['name']}, who you watch a lot")
        return _row(f"person-{hits[0]['id']}", f"More with {hits[0]['name']}", items)

    async def tag_row(tag: str, kind: MediaKind) -> Optional[dict[str, Any]]:
        ids, names = await discovery_keywords(tag)
        if not ids:
            return None
        k = tmdb_kind(kind)
        raw = await tmdb.discover(k, with_keywords="|".join(map(str, ids)), **{"vote_count.gte": 80})
        label = names[0] if names else tag
        items = await refs_from(kind, raw, f"tagged {label}, a theme you like")
        noun = "Movies" if kind == "movie" else "Series"
        return _row(f"tag-{k}-{ids[0]}", f"{noun} about {label}", items)

    async def discovery_keywords(tag: str) -> tuple[list[int], list[str]]:
        from maestarr.taste.recommend import resolve_keywords

        return await resolve_keywords(tmdb, [tag])

    tasks: list[Awaitable[Any]] = [picks("movie"), picks("series")]
    seeds = [s for s in profile.seeds if s.tmdb_id][:2]
    tasks += [because(s) for s in seeds]
    people = [p for p in profile.top("people", 6)][:1]
    tasks += [person_row(p) for p in people]
    tags = [t for t in profile.top("keywords", 12) if t.lower() not in GENERIC_TAGS][:2]
    kinds: list[MediaKind] = ["movie", "series"]
    tasks += [tag_row(t, kind) for t, kind in zip(tags, kinds)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    rows: list[dict[str, Any]] = []
    movie_picks, series_picks, *rest = results
    if isinstance(movie_picks, list) and (row := _row("picks-movie", "Top picks for you", movie_picks, "Movies")):
        rows.append(row)
    if isinstance(series_picks, list) and (row := _row("picks-series", "Series for you", series_picks)):
        rows.append(row)
    for r in rest:
        if isinstance(r, dict):
            rows.append(r)
        elif isinstance(r, BaseException):
            logger.info("a discover row failed: %s", r)
    waiting = await unwatched_in_library(svc)
    if waiting:
        rows.insert(1, {"id": "waiting", "title": "Waiting in your library",
                        "subtitle": "Downloaded a while ago, not watched yet", "items": waiting})
    out = {"rows": rows, "tags": tags_for_filter(profile), "genres": profile.top("genres", 10),
           "based_on": [f"{s.title} ({s.year})" for s in profile.seeds[:4]]}
    return out


def tags_for_filter(profile: Any) -> list[str]:
    """The user's own strongest themes, offered as one-tap filters."""
    return [t for t in profile.top("keywords", 30) if t.lower() not in GENERIC_TAGS][:16]


async def unwatched_in_library(svc: Services, limit: int = 14) -> list[dict[str, Any]]:
    """Titles with files that were added weeks ago and never watched — "watch tonight"."""
    watched = await discovery.watched_set(svc)
    library = await discovery.library_history(svc, limit=400)
    now = datetime.now(timezone.utc)
    out: list[dict[str, Any]] = []
    for ev in library:
        if not ev.tmdb_id or not ev.watched_at:
            continue
        if (now - ev.watched_at).days < UNWATCHED_AFTER_DAYS:
            continue
        k = tmdb_kind(ev.kind)
        if (k, ev.tmdb_id) in watched:
            continue
        days = (now - ev.watched_at).days
        out.append({"kind": ev.kind, "title": ev.title, "year": ev.year, "tmdb_id": ev.tmdb_id, "tvdb_id": ev.tvdb_id,
                    "in_library": True, "why": [f"in your library for {days} days, not watched yet"], "_days": days})
    out.sort(key=lambda r: -r.pop("_days"))  # longest-waiting first
    if svc.tmdb:
        cache = discovery._cache(svc)
        details = await asyncio.gather(*(cache.details(tmdb_kind(r["kind"]), r["tmdb_id"]) for r in out[:limit]))
        for r, det in zip(out, details):
            if det and det.get("poster_path"):
                r["poster_url"] = f"https://image.tmdb.org/t/p/w342{det['poster_path']}"
                r["rating"] = det.get("vote_average")
                r["genres"] = [g["name"] for g in det.get("genres", [])]
    return out[:limit]


READY_SCAN = 150  # how many of the newest unwatched downloads are scored


async def ready_to_watch(svc: Services, tags: Optional[list[str]] = None, limit: int = 12) -> list[dict[str, Any]]:
    """Downloaded titles not watched yet, best match for the user's taste first —
    what "Picks for tonight" offers before anything that still has to be fetched."""
    from maestarr.clients.tmdb import credits_people

    profile = await discovery.taste_profile(svc)
    watched = await discovery.watched_set(svc)
    hidden = (await discovery.feedback_store(svc).state()).hidden
    _, ids = await discovery.library_index(svc)
    library = await discovery.library_history(svc, limit=400)
    candidates = [
        ev for ev in library
        if ev.tmdb_id and (tmdb_kind(ev.kind), ev.tmdb_id) not in watched
        and (tmdb_kind(ev.kind), ev.tmdb_id) not in hidden
    ][:READY_SCAN]
    cache = discovery._cache(svc)
    details = await asyncio.gather(*(cache.details(tmdb_kind(ev.kind), ev.tmdb_id) for ev in candidates))  # type: ignore[arg-type]
    wanted = {t.lower() for t in tags or []}
    scored: list[tuple[float, dict[str, Any]]] = []
    for ev, det in zip(candidates, details):
        if not det:
            continue
        ref = await cache.tmdb.to_ref(tmdb_kind(ev.kind), det, anime=ev.kind == "anime")
        if wanted and not wanted & {x.lower() for x in ref.keywords + ref.genres}:
            continue
        score, why = taste_score(ref, credits_people(det), profile)
        ref.in_library = True
        row = discovery._ref_out(ref)
        row["match"] = round(score * 100)
        row["why"] = ["downloaded, ready to watch", *why]
        row["ready"] = True
        if ev.kind == "movie" and ev.tmdb_id in ids["movie_by_tmdb"]:
            row["movie_id"] = ids["movie_by_tmdb"][ev.tmdb_id]
        scored.append((score, row))
    scored.sort(key=lambda s: -s[0])
    return [row for _, row in scored[:limit]]
