"""Read-only data for the UI's panels: status, overview, queue, recommendations,
preferences."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from maestarr import __version__
from maestarr.api.deps import require_user
from maestarr.clients.base import ServiceError
from maestarr.llm import model_label
from maestarr.services import get_services

router = APIRouter(prefix="/api", tags=["dashboard"])

OVERVIEW_TTL = 20.0
DETAILS_TTL = 3600.0  # lookups take ~20 s on a busy Sonarr/Radarr
PART_DEADLINE = 90.0  # arr calls on a busy host
HISTORY_DEADLINE = 10.0  # Jellyfin history fills its own cache in the background
FIRST_LOAD_WAIT = 25.0


@router.get("/status")
async def status(_: Any = Depends(require_user)) -> dict[str, Any]:
    from maestarr.agent.agent import get_agent

    svc = get_services()
    return {
        "version": __version__,
        "model": model_label(svc.settings),
        "model_ready": get_agent().model is not None,
        "adult_content": svc.settings.MAESTARR_ADULT_CONTENT,
        "services": [s.model_dump() for s in await svc.status()],
    }


def _poster(images: list[dict[str, Any]]) -> Optional[str]:
    for img in images or []:
        if img.get("coverType") == "poster":
            return img.get("remoteUrl") or img.get("url")
    return None


@router.get("/overview")
async def overview(_: Any = Depends(require_user)) -> dict[str, Any]:
    """Library counts, disks, active downloads and recent watching for the home screen."""
    svc = get_services()
    cached = svc.memo.get("overview")
    if cached:
        # Serve the last result at once; refresh in the background when it is old.
        if time.monotonic() - cached[0] >= OVERVIEW_TTL and not _refreshing(svc):
            svc.memo["overview_task"] = asyncio.ensure_future(_build_overview(svc))
        return cached[1]
    if not _refreshing(svc):
        svc.memo["overview_task"] = asyncio.ensure_future(_build_overview(svc))
    task: asyncio.Future[dict[str, Any]] = svc.memo["overview_task"]
    try:
        return await asyncio.wait_for(asyncio.shield(task), timeout=FIRST_LOAD_WAIT)
    except asyncio.TimeoutError:
        return {"counts": {}, "disks": [], "queue": [], "recently_watched": [], "recently_added": [], "loading": True}


def _refreshing(svc: Any) -> bool:
    task = svc.memo.get("overview_task")
    return task is not None and not task.done()


async def _build_overview(svc: Any) -> dict[str, Any]:
    from maestarr.ops import discovery, library

    async def safe(coro: Any, default: Any, deadline: float = PART_DEADLINE) -> Any:
        # A slow part (Jellyfin history can take minutes) must not hold the page; it
        # keeps running shielded and fills its cache for the next visit.
        task = asyncio.ensure_future(coro)
        try:
            return await asyncio.wait_for(asyncio.shield(task), timeout=deadline)
        except Exception:  # noqa: BLE001 — one dead or slow service must not blank the page
            return default

    async def nothing() -> list[Any]:
        return []

    series, movies, queue, disks, history = await asyncio.gather(
        safe(svc.sonarr.series(), []) if svc.sonarr else nothing(),
        safe(svc.radarr.movies(), []) if svc.radarr else nothing(),
        safe(library.queue(svc), []),
        safe(library.disk_usage(svc), []),
        safe(discovery.recent_history(svc, 12), [], HISTORY_DEADLINE) if svc.jellyfin else nothing(),
    )
    recent_series = sorted(series, key=lambda s: s.get("added", ""), reverse=True)[:12]
    recent_movies = sorted([m for m in movies if m.get("hasFile")], key=lambda m: m.get("added", ""), reverse=True)[:12]
    result = {
        "counts": {
            "series": len(series),
            "episodes_on_disk": sum((s.get("statistics") or {}).get("episodeFileCount", 0) for s in series),
            "movies": len(movies),
            "movies_on_disk": sum(1 for m in movies if m.get("hasFile")),
        },
        "disks": disks,
        "queue": queue[:8],
        "recently_watched": history,
        "recently_added": [
            {"kind": "anime" if s.get("seriesType") == "anime" else "series", "id": s["id"], "title": s["title"],
             "year": s.get("year"), "poster": _poster(s.get("images", [])), "tvdb_id": s.get("tvdbId"), "tmdb_id": s.get("tmdbId")}
            for s in recent_series
        ]
        + [
            {"kind": "movie", "id": m["id"], "title": m["title"], "year": m.get("year"),
             "poster": _poster(m.get("images", [])), "tmdb_id": m.get("tmdbId")}
            for m in recent_movies
        ],
    }
    svc.memo["overview"] = (time.monotonic(), result)
    return result


@router.get("/queue")
async def queue(_: Any = Depends(require_user)) -> dict[str, Any]:
    from maestarr.ops import downloads, library

    svc = get_services()
    out: dict[str, Any] = {"queue": [], "disks": []}
    try:
        out["queue"] = await library.queue(svc)
        out["disks"] = await library.disk_usage(svc)
        if svc.qbittorrent:
            t = await downloads.torrents(svc, only_active=True, limit=10)
            out["download_mbps"] = t["download_mbps"]
    except ServiceError as exc:
        out["error"] = str(exc)
    return out


@router.get("/recommendations")
async def recommendations(
    kind: str = "movie",
    mood: Optional[str] = None,
    tags: Optional[str] = None,
    limit: int = 12,
    _: Any = Depends(require_user),
) -> Any:
    from maestarr.ops.discovery import recommendations as recs, record_impressions

    svc = get_services()
    try:
        out = await recs(svc, kind=kind, mood=mood, limit=limit,  # type: ignore[arg-type]
                         tags=[t.strip() for t in (tags or "").split(",") if t.strip()])
    except ServiceError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=503)
    await record_impressions(svc, out["recommendations"])
    return out


@router.get("/discover/rows")
async def discover_rows(refresh: bool = False, _: Any = Depends(require_user)) -> Any:
    from maestarr.ops.discovery import record_impressions
    from maestarr.taste.rows import build_rows

    svc = get_services()
    try:
        out = await build_rows(svc, refresh=refresh)
    except ServiceError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=503)
    await record_impressions(svc, [i for row in out["rows"] for i in row["items"][:8]])
    return out


@router.get("/discover/taste")
async def discover_taste(_: Any = Depends(require_user)) -> Any:
    """The user's strongest tags, genres and people — quick filters for picks and search."""
    from maestarr.ops.discovery import taste_profile
    from maestarr.taste.rows import tags_for_filter

    try:
        p = await taste_profile(get_services())
    except ServiceError as exc:
        return JSONResponse({"detail": str(exc).split(": ", 1)[-1]}, status_code=503)
    return {"tags": tags_for_filter(p), "genres": p.top("genres", 10), "people": p.top("people", 8)}


@router.get("/discover/search")
async def discover_search(
    kind: str = "movie",
    query: Optional[str] = None,
    genres: Optional[str] = None,
    tags: Optional[str] = None,
    people: Optional[str] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    min_rating: Optional[float] = None,
    language: Optional[str] = None,
    max_runtime: Optional[int] = None,
    sort: str = "relevance",
    limit: int = 30,
    _: Any = Depends(require_user),
) -> Any:
    from maestarr.ops.search import discover_titles

    def split(v: Optional[str]) -> Optional[list[str]]:
        return [x.strip() for x in v.split(",") if x.strip()] if v else None

    try:
        return await discover_titles(
            get_services(), kind=kind, query=query or None, genres=split(genres), tags=split(tags),  # type: ignore[arg-type]
            people=split(people), year_from=year_from, year_to=year_to, min_rating=min_rating,
            language=language or None, max_runtime=max_runtime, sort=sort, limit=limit,  # type: ignore[arg-type]
        )
    except ServiceError as exc:
        return JSONResponse({"detail": str(exc).split(": ", 1)[-1]}, status_code=503)


@router.get("/discover/suggest")
async def discover_suggest(type: str, q: str, _: Any = Depends(require_user)) -> Any:
    from maestarr.ops.search import find_people, find_tags

    if len(q.strip()) < 2:
        return []
    try:
        if type == "person":
            return await find_people(get_services(), q.strip(), limit=8)
        return await find_tags(get_services(), q.strip(), limit=10)
    except ServiceError as exc:
        return JSONResponse({"detail": str(exc).split(": ", 1)[-1]}, status_code=503)


@router.get("/discover/genres")
async def discover_genres(kind: str = "movie", _: Any = Depends(require_user)) -> Any:
    from maestarr.clients.tmdb import tmdb_kind

    try:
        names = await get_services().need_tmdb().genres(tmdb_kind(kind))  # type: ignore[arg-type]
    except ServiceError as exc:
        return JSONResponse({"detail": str(exc).split(": ", 1)[-1]}, status_code=503)
    return sorted(names.values())


class Feedback(BaseModel):
    kind: str
    tmdb_id: int
    action: str  # open | search | add | dismiss
    title: Optional[str] = None


@router.post("/feedback")
async def feedback(body: Feedback, _: Any = Depends(require_user)) -> Any:
    """The user opened, searched, added or turned down a suggestion."""
    from maestarr.ops.discovery import react

    if body.action not in ("open", "search", "add", "dismiss"):
        return JSONResponse({"detail": "unknown action"}, status_code=400)
    svc = get_services()
    out = await react(svc, body.kind, body.tmdb_id, body.action, body.title)
    svc.memo.pop("rows", None)
    return out


@router.get("/details")
async def title_details(
    kind: str,
    tmdb_id: Optional[int] = None,
    tvdb_id: Optional[int] = None,
    stash_id: Optional[str] = None,
    title: Optional[str] = None,
    year: Optional[int] = None,
    _: Any = Depends(require_user),
) -> Any:
    from maestarr.ops.details import details

    if kind not in ("movie", "series", "anime", "scene"):
        return JSONResponse({"detail": "unknown kind"}, status_code=400)
    svc = get_services()
    key = f"details:{kind}:{tmdb_id}:{tvdb_id}:{stash_id}:{(title or '').lower()}:{year}"
    cached = svc.memo.get(key)
    if cached and time.monotonic() - cached[0] < DETAILS_TTL:
        return cached[1]
    try:
        out = await details(svc, kind, tmdb_id=tmdb_id, tvdb_id=tvdb_id,  # type: ignore[arg-type]
                            stash_id=stash_id, title=title, year=year)
        svc.memo[key] = (time.monotonic(), out)
        return out
    except ServiceError as exc:
        return JSONResponse({"detail": str(exc).split(": ", 1)[-1]}, status_code=503)


@router.get("/adult")
async def adult(query: Optional[str] = None, limit: int = 18, _: Any = Depends(require_user)) -> Any:
    from maestarr.ops.discovery import adult_picks

    try:
        return await adult_picks(get_services(), query or None, max(1, min(limit, 40)))
    except ServiceError as exc:
        return JSONResponse({"detail": str(exc).split(": ", 1)[-1]}, status_code=503)


@router.get("/preferences")
async def get_preferences(_: Any = Depends(require_user)) -> dict[str, Any]:
    return get_services().preferences().model_dump()


@router.put("/preferences")
async def put_preferences(body: dict[str, Any], _: Any = Depends(require_user)) -> dict[str, Any]:
    from maestarr.ops.downloads import update_preferences

    return update_preferences(get_services(), body)
