"""Recommendation cards: the agent names its picks and why, this fills in the
poster, description and library state from the same places Sonarr, Radarr and
Whisparr take them (their lookups, StashDB), with TMDB as a fallback.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from maestarr.clients.base import ServiceError
from maestarr.clients.tmdb import tmdb_kind
from maestarr.services import Services

logger = logging.getLogger(__name__)

CARD_TIMEOUT = 45


def _small(url: Optional[str]) -> Optional[str]:
    """TMDB serves originals by default; a card needs a w500.

    >>> _small("https://image.tmdb.org/t/p/original/x.jpg")
    'https://image.tmdb.org/t/p/w500/x.jpg'
    """
    return url.replace("/t/p/original/", "/t/p/w500/") if url else url


class Pick(BaseModel):
    kind: Literal["movie", "series", "anime", "scene"]
    title: str
    why: str = Field(description="One sentence: why this fits the user's request")
    year: Optional[int] = None
    tmdb_id: Optional[int] = None
    tvdb_id: Optional[int] = None
    stash_id: Optional[str] = Field(default=None, description="StashDB scene id, for scenes")


def _image(images: list[dict[str, Any]], *types: str) -> Optional[str]:
    for wanted in types:
        for img in images or []:
            if img.get("coverType") == wanted and (img.get("remoteUrl") or img.get("url")):
                return str(img.get("remoteUrl") or img.get("url"))
    return None


def _arr_card(item: dict[str, Any]) -> dict[str, Any]:
    ratings = item.get("ratings") or {}
    rating = (ratings.get("imdb") or {}).get("value") if "imdb" in ratings else ratings.get("value")
    return {
        "title": item.get("title"),
        "year": item.get("year"),
        "image": _image(item.get("images") or [], "poster", "fanart", "screenshot"),
        "overview": item.get("overview"),
        "rating": round(float(rating), 1) if rating else None,
        "in_library": bool(item.get("id")),
        "tmdb_id": item.get("tmdbId"),
        "tvdb_id": item.get("tvdbId"),
    }


async def _movie(svc: Services, p: Pick) -> dict[str, Any]:
    if svc.radarr:
        if p.tmdb_id:
            return _arr_card(await svc.radarr.lookup_tmdb(p.tmdb_id))
        found = await svc.radarr.lookup(f"{p.title} {p.year or ''}".strip())
        if found:
            return _arr_card(found[0])
    return await _tmdb(svc, p)


async def _series(svc: Services, p: Pick) -> dict[str, Any]:
    if svc.sonarr:
        found = await svc.sonarr.lookup(f"tvdb:{p.tvdb_id}" if p.tvdb_id else p.title)
        if p.year and not p.tvdb_id:
            found = [f for f in found if f.get("year") == p.year] or found
        if found:
            return _arr_card(found[0])
    return await _tmdb(svc, p)


async def _tmdb(svc: Services, p: Pick) -> dict[str, Any]:
    if not svc.tmdb:
        return {}
    kind = tmdb_kind(p.kind)  # type: ignore[arg-type]
    if p.tmdb_id:
        det = await svc.tmdb.details(kind, p.tmdb_id)
    else:
        hits = await svc.tmdb.search(kind, p.title, p.year)
        if not hits:
            return {}
        det = hits[0]
    ref = await svc.tmdb.to_ref(kind, det, anime=p.kind == "anime")
    return {"title": ref.title, "year": ref.year, "image": ref.poster_url, "overview": ref.overview,
            "rating": ref.rating, "tmdb_id": ref.tmdb_id, "tvdb_id": ref.tvdb_id}


async def _scene(svc: Services, p: Pick) -> dict[str, Any]:
    if not svc.settings.MAESTARR_ADULT_CONTENT:
        raise ServiceError("stashdb", "adult content is switched off")
    scene = None
    if svc.stashdb:
        scene = await svc.stashdb.scene(p.stash_id) if p.stash_id else None
        if scene is None:
            hits = await svc.stashdb.search_scenes(p.title, limit=1)
            scene = hits[0] if hits else None
    card: dict[str, Any] = {}
    if scene:
        card = {"title": scene["title"], "image": scene["image"], "overview": scene["overview"],
                "stash_id": scene["id"], "studio": scene["studio"], "date": scene["date"],
                "performers": scene["performers"][:4], "minutes": scene["minutes"]}
        card["year"] = int(scene["date"][:4]) if scene.get("date") else None
    if svc.whisparr and card.get("stash_id"):
        with_lib = await svc.whisparr.item_by_stash_id(card["stash_id"])
        card["in_library"] = bool(with_lib)
    return card


async def _card(svc: Services, p: Pick) -> Optional[dict[str, Any]]:
    resolve = {"movie": _movie, "series": _series, "anime": _series, "scene": _scene}[p.kind]
    try:
        # A slow lookup must not hold up the other cards; show what the agent gave instead.
        found = await asyncio.wait_for(resolve(svc, p), timeout=CARD_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning("card lookup timed out for %s", p.title)
        found = {}
    except ServiceError as exc:
        if p.kind == "scene" and "switched off" in str(exc):
            return None
        logger.warning("card lookup failed for %s: %s", p.title, exc)
        found = {}
    card: dict[str, Any] = {"kind": p.kind, "title": p.title, "year": p.year, "why": p.why,
                            "tmdb_id": p.tmdb_id, "tvdb_id": p.tvdb_id, "stash_id": p.stash_id}
    card.update({k: v for k, v in found.items() if v not in (None, "", [])})
    card["title"] = found.get("title") or p.title  # the source's own spelling
    card["image"] = _small(card.get("image"))
    if card.get("overview"):
        card["overview"] = str(card["overview"])[:420]
    return card


async def present(svc: Services, picks: list[Pick]) -> dict[str, Any]:
    cards = await asyncio.gather(*(_card(svc, p) for p in picks[:12]))
    return {
        "cards": [c for c in cards if c],
        "note": "The user now sees these as cards with posters, descriptions and your reasons. "
        "Reply in one or two sentences; do not list the titles or repeat their details.",
    }
