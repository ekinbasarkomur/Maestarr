"""A persistent cache for slow things: watch history, libraries, the taste
profile and the suggestion shelves.

Values live in SQLite, so a restart (or a settings change, which rebuilds the
service clients) does not throw them away. Reads are stale-while-revalidate:

- fresh → returned;
- stale → returned at once, and one rebuild starts in the background;
- missing → built now (concurrent callers share the same build).

Nothing refreshes unless someone asks, except the optional background refresh
(Settings → General → Caching), which keeps the data warm on a schedule.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

import aiosqlite

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);
"""

# In-process copies and running builds, kept across service rebuilds.
_memory: dict[str, tuple[float, Any]] = {}
_building: dict[str, asyncio.Task[Any]] = {}


class CacheStore:
    def __init__(self, path: Path):
        self.path = path
        self._ready = False

    async def _db(self) -> aiosqlite.Connection:
        db = await aiosqlite.connect(self.path, timeout=30)
        if not self._ready:
            await db.executescript(SCHEMA)
            await db.commit()
            self._ready = True
        return db

    async def get(self, key: str) -> Optional[tuple[float, Any]]:
        db = await self._db()
        try:
            async with db.execute("SELECT value, updated_at FROM cache WHERE key = ?", (key,)) as cur:
                row = await cur.fetchone()
        finally:
            await db.close()
        return (row[1], json.loads(row[0])) if row else None

    async def put(self, key: str, value: Any, updated_at: Optional[float] = None) -> None:
        db = await self._db()
        try:
            await db.execute(
                "INSERT INTO cache (key, value, updated_at) VALUES (?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (key, json.dumps(value, default=str), updated_at or time.time()),
            )
            await db.commit()
        finally:
            await db.close()

    async def ages(self) -> dict[str, float]:
        db = await self._db()
        try:
            async with db.execute("SELECT key, updated_at FROM cache") as cur:
                rows = await cur.fetchall()
        finally:
            await db.close()
        return {k: t for k, t in rows}

    async def drop(self, prefix: str) -> None:
        db = await self._db()
        try:
            await db.execute("DELETE FROM cache WHERE key LIKE ?", (prefix + "%",))
            await db.commit()
        finally:
            await db.close()
        for k in [k for k in _memory if k.startswith(f"{self.path}|{prefix}")]:
            _memory.pop(k, None)


_stores: dict[Path, CacheStore] = {}


def store_for(path: Path) -> CacheStore:
    if path not in _stores:
        _stores[path] = CacheStore(path)
    return _stores[path]


async def cached(
    store: CacheStore,
    key: str,
    *,
    max_age: Optional[float],
    build: Callable[[], Awaitable[Any]],
    encode: Callable[[Any], Any] = lambda v: v,
    decode: Callable[[Any], Any] = lambda v: v,
) -> Any:
    """The value for `key`, built with `build` when missing; stale values are
    returned while a fresh one is built in the background. `max_age=None`
    means "never stale" (refreshed only by hand)."""
    mkey = f"{store.path}|{key}"
    entry = _memory.get(mkey)
    if entry is None:
        stored = await store.get(key)
        if stored is not None:
            try:
                entry = (stored[0], decode(stored[1]))
            except Exception:  # noqa: BLE001 — an old or broken entry is rebuilt
                logger.warning("cache entry %s unreadable; rebuilding", key)
                entry = None
            if entry is not None:
                _memory[mkey] = entry
    if entry is not None:
        if max_age is not None and time.time() - entry[0] > max_age:
            refresh_in_background(store, key, build, encode)
        return entry[1]
    return await _build(store, key, build, encode)


def refresh_in_background(
    store: CacheStore, key: str, build: Callable[[], Awaitable[Any]], encode: Callable[[Any], Any] = lambda v: v
) -> None:
    mkey = f"{store.path}|{key}"
    if mkey in _building and not _building[mkey].done():
        return
    task = asyncio.ensure_future(_build(store, key, build, encode))
    task.add_done_callback(lambda t: _report(key, t))


def _report(key: str, task: "asyncio.Task[Any]") -> None:
    if not task.cancelled() and task.exception() is not None:
        logger.warning("refreshing %s failed: %s", key, task.exception())


async def _build(store: CacheStore, key: str, build: Callable[[], Awaitable[Any]], encode: Callable[[Any], Any]) -> Any:
    mkey = f"{store.path}|{key}"
    running = _building.get(mkey)
    if running is not None and not running.done():
        return await asyncio.shield(running)

    async def run() -> Any:
        value = await build()
        now = time.time()
        _memory[mkey] = (now, value)
        await store.put(key, encode(value), now)
        return value

    task = _building[mkey] = asyncio.ensure_future(run())
    try:
        return await asyncio.shield(task)
    finally:
        if task.done():
            _building.pop(mkey, None)


def is_building(store: CacheStore, prefix: str = "") -> bool:
    return any(k.startswith(f"{store.path}|{prefix}") and not t.done() for k, t in _building.items())


def forget_memory() -> None:
    """Drop in-process copies (tests); SQLite keeps the values."""
    _memory.clear()
