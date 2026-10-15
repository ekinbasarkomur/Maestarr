"""Rebuilding the caches: by hand ("Refresh now") or on the optional schedule.

Order matters: watch history and libraries first, then the taste profile built
from them, then the shelves built from the profile.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

from maestarr.cache import is_building
from maestarr.services import Services

logger = logging.getLogger(__name__)

DATA_KEYS = ("data:watch_history", "data:taste_events", "data:watched_set", "data:taste_profile")
CHECK_EVERY = 600.0  # the scheduler looks every 10 minutes whether a refresh is due

_running: Optional[asyncio.Task[None]] = None
_last_error: Optional[str] = None


async def refresh_all(svc: Services) -> None:
    """Throw away and rebuild everything, in dependency order."""
    global _last_error
    from maestarr.ops import discovery
    from maestarr.taste.rows import build_rows

    store = discovery.cache_store(svc)
    started = time.time()
    try:
        await store.drop("data:")
        await discovery.watch_history(svc)
        await discovery.taste_events(svc)
        await discovery.watched_set(svc)
        await discovery.taste_profile(svc)
        await store.drop("picks:")
        if svc.tmdb:
            await build_rows(svc)
        _last_error = None
        logger.info("caches refreshed in %.0f s", time.time() - started)
    except Exception as exc:  # noqa: BLE001 — report it in the settings page
        _last_error = str(exc)[:300]
        logger.warning("cache refresh failed: %s", exc)


def start_refresh(svc: Services) -> bool:
    """Start a full refresh in the background; False when one is already running."""
    global _running
    if _running is not None and not _running.done():
        return False
    _running = asyncio.ensure_future(refresh_all(svc))
    return True


async def status(svc: Services) -> dict[str, Any]:
    from maestarr.ops import discovery

    store = discovery.cache_store(svc)
    ages = await store.ages()
    data = [ages[k] for k in DATA_KEYS if k in ages]
    picks = [t for k, t in ages.items() if k.startswith("picks:")]
    return {
        "running": (_running is not None and not _running.done()) or is_building(store),
        "data_refreshed_at": min(data) if data else None,
        "picks_refreshed_at": max(picks) if picks else None,
        "last_error": _last_error,
    }


async def scheduler(get_services: Any) -> None:
    """Background refresh: when switched on, rebuild once the data is older than the interval."""
    while True:
        await asyncio.sleep(CHECK_EVERY)
        try:
            svc = get_services()
            s = svc.settings
            if not s.MAESTARR_BACKGROUND_REFRESH:
                continue
            info = await status(svc)
            oldest = info["data_refreshed_at"]
            due = oldest is None or time.time() - oldest > max(1, s.MAESTARR_DATA_REFRESH_HOURS) * 3600
            if due and not info["running"]:
                logger.info("background refresh due")
                start_refresh(svc)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — the loop must survive anything
            logger.exception("refresh scheduler")
