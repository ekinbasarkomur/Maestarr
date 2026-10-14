"""Read-only data for the UI's panels: status, overview, queue, recommendations,
preferences."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from maestarr import __version__
from maestarr.api.deps import require_user
from maestarr.clients.base import ServiceError
from maestarr.llm import model_label
from maestarr.services import get_services

router = APIRouter(prefix="/api", tags=["dashboard"])

OVERVIEW_TTL = 20.0


@router.get("/status")
async def status(_: Any = Depends(require_user)) -> dict[str, Any]:
    from maestarr.agent.agent import get_agent

    svc = get_services()
    return {
        "version": __version__,
        "model": model_label(svc.settings),
        "model_ready": get_agent().model is not None,
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
    from maestarr.ops import discovery, library

    svc = get_services()
    cached = svc.memo.get("overview")
    if cached and time.monotonic() - cached[0] < OVERVIEW_TTL:
        return cached[1]

    async def safe(coro: Any, default: Any) -> Any:
        try:
            return await coro
        except Exception:  # noqa: BLE001 — one dead service must not blank the page
            return default

    async def nothing() -> list[Any]:
        return []

    series, movies, queue, disks, history = await asyncio.gather(
        safe(svc.sonarr.series(), []) if svc.sonarr else nothing(),
        safe(svc.radarr.movies(), []) if svc.radarr else nothing(),
        safe(library.queue(svc), []),
        safe(library.disk_usage(svc), []),
        safe(discovery.recent_history(svc, 12), []) if svc.jellyfin else nothing(),
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
            {"kind": "series", "id": s["id"], "title": s["title"], "year": s.get("year"), "poster": _poster(s.get("images", []))}
            for s in recent_series
        ]
        + [
            {"kind": "movie", "id": m["id"], "title": m["title"], "year": m.get("year"), "poster": _poster(m.get("images", []))}
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
    kind: str = "movie", mood: Optional[str] = None, limit: int = 12, _: Any = Depends(require_user)
) -> Any:
    from maestarr.ops.discovery import recommendations as recs

    try:
        return await recs(get_services(), kind=kind, mood=mood, limit=limit)  # type: ignore[arg-type]
    except ServiceError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=503)


@router.get("/preferences")
async def get_preferences(_: Any = Depends(require_user)) -> dict[str, Any]:
    return get_services().preferences().model_dump()


@router.put("/preferences")
async def put_preferences(body: dict[str, Any], _: Any = Depends(require_user)) -> dict[str, Any]:
    from maestarr.ops.downloads import update_preferences

    return update_preferences(get_services(), body)
