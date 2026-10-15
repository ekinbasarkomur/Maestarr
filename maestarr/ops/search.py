"""Detailed title search: text, tags, people, genres, years, rating, language,
runtime and sort — shared by the Discover page and the agent.

Built on TMDB's discover (through a TMDB key or Seerr). Seerr's discover has no
people filter, so with Seerr a person search walks their filmography instead.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal, Optional

from maestarr.clients.base import ServiceError
from maestarr.clients.tmdb import IMAGE_BASE, tmdb_kind
from maestarr.domain import MediaKind
from maestarr.ops.discovery import _imdb, _ref_out, library_index, watched_set
from maestarr.services import Services
from maestarr.taste.recommend import resolve_keywords

Sort = Literal["relevance", "rating", "newest", "oldest"]

_SORT = {
    "relevance": "popularity.desc",
    "rating": "vote_average.desc",
    "newest": "{date}.desc",
    "oldest": "{date}.asc",
}


async def find_people(svc: Services, name: str, limit: int = 6) -> list[dict[str, Any]]:
    """People matching a name, with what they are known for."""
    hits = await svc.need_tmdb().search_people(name)
    return [
        {
            "id": p["id"],
            "name": p.get("name"),
            "department": p.get("known_for_department"),
            "known_for": [k.get("title") or k.get("name") for k in (p.get("known_for") or [])[:3]],
            "image": f"https://image.tmdb.org/t/p/w185{p['profile_path']}" if p.get("profile_path") else None,
        }
        for p in hits[:limit]
    ]


async def find_tags(svc: Services, query: str, limit: int = 10) -> list[dict[str, Any]]:
    """TMDB keywords (the tags titles carry) matching a word."""
    hits = await svc.need_tmdb().search_keywords(query)
    exact = [h for h in hits if h["name"].lower() == query.lower()]
    rest = [h for h in hits if h not in exact]
    return [{"id": h["id"], "name": h["name"]} for h in (exact + rest)[:limit]]


async def discover_titles(
    svc: Services,
    *,
    kind: MediaKind = "movie",
    query: Optional[str] = None,
    genres: Optional[list[str]] = None,
    tags: Optional[list[str]] = None,
    people: Optional[list[str]] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    min_rating: Optional[float] = None,
    language: Optional[str] = None,
    max_runtime: Optional[int] = None,
    sort: Sort = "relevance",
    limit: int = 20,
) -> dict[str, Any]:
    tmdb = svc.need_tmdb()
    k = tmdb_kind(kind)
    date_key = "primary_release_date" if k == "movie" else "first_air_date"
    applied: dict[str, Any] = {}

    genre_ids = await tmdb.genre_ids(k, genres or []) if genres else []
    if kind == "anime":
        genre_ids = sorted(set(genre_ids) | {16})
        language = language or "ja"
    tag_ids, tag_names = await resolve_keywords(tmdb, tags) if tags else ([], [])
    person_hits = await asyncio.gather(*(tmdb.search_people(p) for p in (people or [])[:3]))
    persons = [(hits[0]["id"], hits[0]["name"]) for hits in person_hits if hits]
    if genres:
        applied["genres"] = genres
    if tag_names:
        applied["tags"] = tag_names
    if persons:
        applied["people"] = [n for _, n in persons]
    if people and not persons:
        raise ServiceError("tmdb", f"no person found for {', '.join(people)}")

    filters: dict[str, Any] = {
        "with_genres": "|".join(map(str, genre_ids)) or None,
        "with_keywords": "|".join(map(str, tag_ids)) or None,
        "vote_average.gte": min_rating,
        "vote_count.gte": 40 if sort in ("rating", "relevance") else None,
        f"{date_key}.gte": f"{year_from}-01-01" if year_from else None,
        f"{date_key}.lte": f"{year_to}-12-31" if year_to else None,
        "with_original_language": language,
        "with_runtime.lte": max_runtime,
        "sort_by": _SORT[sort].format(date=date_key),
    }

    if query and not (genre_ids or tag_ids or persons):
        items = await tmdb.search(k, query, year_from if year_from and year_from == year_to else None)
        items = [i for i in items if _passes(i, k, filters, genre_ids)]
    elif persons and (tmdb.name == "seerr" or query):
        # Seerr cannot filter discover by person: walk the filmography instead.
        credits = await asyncio.gather(*(tmdb.person_credits(pid) for pid, _ in persons))
        seen: dict[int, dict[str, Any]] = {}
        for c in credits:
            for item in (c.get("cast") or []) + (c.get("crew") or []):
                if item.get("media_type", k) == k and item.get("id") not in seen:
                    seen[item["id"]] = item
        items = [i for i in seen.values() if _passes(i, k, filters, genre_ids, tag_ids)]
        items.sort(key=lambda i: -(i.get("popularity") or 0) if sort == "relevance" else -(i.get("vote_average") or 0))
    else:
        if persons:
            filters["with_people"] = ",".join(str(pid) for pid, _ in persons)
        items = await tmdb.discover(k, **filters)

    items = items[: max(1, min(limit, 40))]
    refs = await asyncio.gather(*(tmdb.to_ref(k, i, anime=kind == "anime") for i in items))
    await _imdb(svc, list(refs))
    owned, _ = await library_index(svc)
    watched = await watched_set(svc)
    results = []
    for ref, raw in zip(refs, items):
        if not ref.poster_url and raw.get("poster_path"):
            ref.poster_url = f"{IMAGE_BASE}{raw['poster_path']}"
        ref.in_library = (k, ref.tmdb_id) in owned if ref.tmdb_id else None
        ref.watched = (k, ref.tmdb_id) in watched if ref.tmdb_id else None
        results.append(_ref_out(ref))
    return {"kind": kind, "query": query, "applied": applied, "results": results}


def _passes(item: dict[str, Any], kind: str, filters: dict[str, Any], genre_ids: list[int],
            tag_ids: Optional[list[int]] = None) -> bool:
    """Apply discover's filters to a search/filmography result client-side.

    >>> f = {"vote_average.gte": 7, "primary_release_date.gte": "2000-01-01", "primary_release_date.lte": None}
    >>> _passes({"vote_average": 8, "release_date": "2010-05-01", "genre_ids": [18]}, "movie", f, [18])
    True
    >>> _passes({"vote_average": 6, "release_date": "2010-05-01"}, "movie", f, [])
    False
    """
    date = str(item.get("release_date") or item.get("first_air_date") or "")
    key = "primary_release_date" if kind == "movie" else "first_air_date"
    if filters.get("vote_average.gte") and (item.get("vote_average") or 0) < filters["vote_average.gte"]:
        return False
    if filters.get(f"{key}.gte") and (not date or date < filters[f"{key}.gte"]):
        return False
    if filters.get(f"{key}.lte") and (not date or date > filters[f"{key}.lte"]):
        return False
    if genre_ids and not set(genre_ids) & set(item.get("genre_ids") or []):
        return False
    lang = filters.get("with_original_language")
    if lang and item.get("original_language") and item["original_language"] != lang:
        return False
    return True
