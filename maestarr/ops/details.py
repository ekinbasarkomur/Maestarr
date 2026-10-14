"""Everything the details popup shows for one title or scene.

Movies come from Radarr's lookup and series from Sonarr's (the same images,
genres, ratings and trailer those apps show), with TMDB adding the cast and a
series trailer when a key is set. Scenes come from StashDB.
"""

from __future__ import annotations

import logging
from typing import Any, Literal, Optional

from maestarr.clients.base import ServiceError
from maestarr.services import Services

logger = logging.getLogger(__name__)

TMDB_IMG = "https://image.tmdb.org/t/p/"

DetailKind = Literal["movie", "series", "anime", "scene"]


def _sized(url: Optional[str], size: str) -> Optional[str]:
    """TMDB originals are huge; ask for a sensible size.

    >>> _sized("https://image.tmdb.org/t/p/original/a.jpg", "w1280")
    'https://image.tmdb.org/t/p/w1280/a.jpg'
    >>> _sized("https://artworks.thetvdb.com/x.jpg", "w1280")
    'https://artworks.thetvdb.com/x.jpg'
    """
    return url.replace("/t/p/original/", f"/t/p/{size}/") if url else url


def _image(images: list[dict[str, Any]], kind: str) -> Optional[str]:
    for img in images or []:
        if img.get("coverType") == kind and (img.get("remoteUrl") or img.get("url")):
            return str(img.get("remoteUrl") or img.get("url"))
    return None


def _ratings(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Radarr: {imdb: {value}, tmdb: …, rottenTomatoes: …}; Sonarr: {value, votes}.

    >>> _ratings({"imdb": {"value": 8.6}, "rottenTomatoes": {"value": 84}, "metacritic": {"value": 0}})
    [{'source': 'IMDb', 'value': '8.6'}, {'source': 'Rotten Tomatoes', 'value': '84%'}]
    >>> _ratings({"value": 8.6, "votes": 4})
    [{'source': 'Rating', 'value': '8.6'}]
    """
    if "value" in raw:
        return [{"source": "Rating", "value": f"{raw['value']:.1f}"}] if raw.get("value") else []
    labels = {"imdb": ("IMDb", "{:.1f}"), "tmdb": ("TMDB", "{:.1f}"), "rottenTomatoes": ("Rotten Tomatoes", "{:.0f}%"),
              "metacritic": ("Metacritic", "{:.0f}"), "trakt": ("Trakt", "{:.1f}")}
    out = []
    for key, (label, fmt) in labels.items():
        value = (raw.get(key) or {}).get("value")
        if value:
            out.append({"source": label, "value": fmt.format(value)})
    return out


async def details(
    svc: Services,
    kind: DetailKind,
    *,
    tmdb_id: Optional[int] = None,
    tvdb_id: Optional[int] = None,
    stash_id: Optional[str] = None,
    title: Optional[str] = None,
    year: Optional[int] = None,
) -> dict[str, Any]:
    if kind == "scene":
        return await _scene(svc, stash_id, title)
    if kind == "movie":
        out = await _movie(svc, tmdb_id, title, year)
    else:
        out = await _series(svc, kind, tvdb_id, title, year)
    await _add_tmdb(svc, out)
    return out


async def _movie(svc: Services, tmdb_id: Optional[int], title: Optional[str], year: Optional[int]) -> dict[str, Any]:
    radarr = svc.need_radarr()
    if tmdb_id:
        item = await radarr.lookup_tmdb(tmdb_id)
    else:
        found = await radarr.lookup(f"{title or ''} {year or ''}".strip())
        if not found:
            raise ServiceError("radarr", f"nothing found for {title}")
        item = found[0]
    images = item.get("images") or []
    return {
        "kind": "movie",
        "title": item.get("title"),
        "original_title": item.get("originalTitle"),
        "year": item.get("year"),
        "overview": item.get("overview"),
        "runtime": item.get("runtime") or None,
        "certification": item.get("certification"),
        "genres": item.get("genres") or [],
        "tags": (item.get("keywords") or [])[:12],
        "studio": item.get("studio"),
        "status": item.get("status"),
        "ratings": _ratings(item.get("ratings") or {}),
        "trailer": item.get("youTubeTrailerId") or None,
        "poster": _sized(_image(images, "poster"), "w500"),
        "backdrop": _sized(_image(images, "fanart"), "w1280"),
        "logo": _image(images, "clearlogo"),
        "in_library": bool(item.get("id")),
        "has_file": bool(item.get("hasFile")),
        "tmdb_id": item.get("tmdbId"),
        "imdb_id": item.get("imdbId"),
        "cast": [],
    }


async def _series(
    svc: Services, kind: DetailKind, tvdb_id: Optional[int], title: Optional[str], year: Optional[int]
) -> dict[str, Any]:
    sonarr = svc.need_sonarr()
    found = await sonarr.lookup(f"tvdb:{tvdb_id}" if tvdb_id else (title or ""))
    if year and not tvdb_id:
        found = [f for f in found if f.get("year") == year] or found
    if not found:
        raise ServiceError("sonarr", f"nothing found for {title or tvdb_id}")
    item = found[0]
    images = item.get("images") or []
    seasons = [s for s in item.get("seasons") or [] if s.get("seasonNumber", 0) > 0]
    return {
        "kind": "anime" if kind == "anime" or item.get("seriesType") == "anime" else "series",
        "title": item.get("title"),
        "year": item.get("year"),
        "overview": item.get("overview"),
        "runtime": item.get("runtime") or None,
        "certification": item.get("certification"),
        "genres": item.get("genres") or [],
        "tags": [],
        "network": item.get("network"),
        "status": item.get("status"),
        "seasons": len(seasons) or None,
        "ratings": _ratings(item.get("ratings") or {}),
        "trailer": None,
        "poster": _image(images, "poster"),
        "backdrop": _image(images, "fanart"),
        "logo": _image(images, "clearlogo"),
        "in_library": bool(item.get("id")),
        "tmdb_id": item.get("tmdbId"),
        "tvdb_id": item.get("tvdbId"),
        "imdb_id": item.get("imdbId"),
        "cast": [],
    }


async def _add_tmdb(svc: Services, out: dict[str, Any]) -> None:
    """Cast, keywords, a backdrop and a trailer from TMDB, when a key is set."""
    if not svc.tmdb or not out.get("tmdb_id"):
        return
    kind = "movie" if out["kind"] == "movie" else "tv"
    try:
        det = await svc.tmdb.get_json(
            f"/{kind}/{out['tmdb_id']}", language=svc.tmdb.language, append_to_response="credits,videos,keywords"
        )
    except ServiceError as exc:
        logger.warning("tmdb details failed: %s", exc)
        return
    out["cast"] = [
        {"name": c.get("name"), "role": c.get("character"),
         "image": f"{TMDB_IMG}w185{c['profile_path']}" if c.get("profile_path") else None}
        for c in ((det.get("credits") or {}).get("cast") or [])[:12]
    ]
    out["tagline"] = det.get("tagline") or None
    if not out.get("tags"):
        words = (det.get("keywords") or {}).get("keywords") or (det.get("keywords") or {}).get("results") or []
        out["tags"] = [w["name"] for w in words[:12]]
    if not out.get("backdrop") and det.get("backdrop_path"):
        out["backdrop"] = f"{TMDB_IMG}w1280{det['backdrop_path']}"
    if not out.get("trailer"):
        videos = [v for v in (det.get("videos") or {}).get("results") or [] if v.get("site") == "YouTube"]
        videos.sort(key=lambda v: (v.get("type") != "Trailer", not v.get("official")))
        out["trailer"] = videos[0]["key"] if videos else None


async def _scene(svc: Services, stash_id: Optional[str], title: Optional[str]) -> dict[str, Any]:
    if not svc.settings.MAESTARR_ADULT_CONTENT:
        raise ServiceError("stashdb", "adult content is switched off")
    if not svc.stashdb:
        raise ServiceError("stashdb", "StashDB is not set up")
    scene = await svc.stashdb.scene_full(stash_id) if stash_id else None
    if scene is None and title:
        hits = await svc.stashdb.search_scenes(title, limit=1)
        scene = await svc.stashdb.scene_full(hits[0]["id"]) if hits else None
    if scene is None:
        raise ServiceError("stashdb", "scene not found")
    in_library = False
    if svc.whisparr:
        try:
            in_library = bool(await svc.whisparr.item_by_stash_id(scene["id"]))
        except ServiceError:
            pass
    return {**scene, "kind": "scene", "stash_id": scene["id"], "in_library": in_library, "trailer": None}
