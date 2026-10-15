"""What the user did with past suggestions, and when to show them again.

Every suggestion shown on the home page, Discover or in the chat is an
*impression*. Like a flash-card scheduler, a title the user keeps scrolling past
comes back less and less often (1, 2, 4, 8 … up to 60 days), while one they
open, search or add is a *positive* signal: its themes pull similar titles up.
"Not for me" hides a title for a year and makes its themes count against
similar ones. A title shown in the last 12 hours stays put, so the home page does
not reshuffle on every visit.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal, Optional

import aiosqlite

DAY = 86400.0
STICKY = 12 * 3600.0  # a title shown recently keeps its place for this long
MAX_INTERVAL_DAYS = 60
Action = Literal["open", "search", "add", "dismiss"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS impressions (
    kind TEXT NOT NULL,
    tmdb_id INTEGER NOT NULL,
    title TEXT,
    shown INTEGER NOT NULL DEFAULT 0,
    engaged INTEGER NOT NULL DEFAULT 0,
    dismissed INTEGER NOT NULL DEFAULT 0,
    last_shown REAL,
    last_engaged REAL,
    next_due REAL NOT NULL DEFAULT 0,
    genres TEXT,
    keywords TEXT,
    PRIMARY KEY (kind, tmdb_id)
);
"""


def next_interval_days(shown: int) -> float:
    """Days until a title that was shown `shown` times without a reaction may return.

    >>> [next_interval_days(n) for n in (1, 2, 3, 4, 7, 10)]
    [1.0, 2.0, 4.0, 8.0, 60.0, 60.0]
    """
    return float(min(MAX_INTERVAL_DAYS, 2 ** max(0, shown - 1)))


@dataclass
class FeedbackState:
    hidden: set[tuple[str, int]] = field(default_factory=set)  # not due yet
    liked: list[dict[str, Any]] = field(default_factory=list)  # engaged, with themes
    disliked: list[dict[str, Any]] = field(default_factory=list)  # dismissed, with themes

    def is_hidden(self, kind: str, tmdb_id: Optional[int]) -> bool:
        return tmdb_id is not None and (kind, int(tmdb_id)) in self.hidden


class FeedbackStore:
    def __init__(self, path: Path):
        self.path = path
        self._ready = False

    async def _db(self) -> aiosqlite.Connection:
        db = await aiosqlite.connect(self.path, timeout=30)
        db.row_factory = aiosqlite.Row
        if not self._ready:
            await db.executescript(SCHEMA)
            await db.commit()
            self._ready = True
        return db

    async def shown(self, items: Iterable[tuple[str, int, str]], now: Optional[float] = None) -> None:
        """Count an impression for each (kind, tmdb_id, title), at most once per sticky window."""
        now = now or time.time()
        items = list(items)
        db = await self._db()
        try:
            # Read everything first, then write in one short transaction: holding the
            # write lock across many slow round trips blocked logins and chats.
            async with db.execute("SELECT kind, tmdb_id, shown, last_shown, last_engaged FROM impressions") as cur:
                known = {(r["kind"], int(r["tmdb_id"])): r for r in await cur.fetchall()}
            writes = []
            for kind, tmdb_id, title in items:
                row = known.get((kind, int(tmdb_id)))
                if row and row["last_shown"] and now - row["last_shown"] < STICKY:
                    continue
                shown = (row["shown"] if row else 0) + 1
                # Engaged since it was last shown? Then it is not a "skip".
                engaged_since = bool(row and row["last_engaged"] and row["last_engaged"] >= (row["last_shown"] or 0))
                due = now + (2 * DAY if engaged_since else next_interval_days(shown) * DAY)
                writes.append((kind, tmdb_id, title, shown, now, due))
            if writes:
                await db.executemany(
                    """INSERT INTO impressions (kind, tmdb_id, title, shown, last_shown, next_due)
                       VALUES (?,?,?,?,?,?)
                       ON CONFLICT(kind, tmdb_id) DO UPDATE SET
                         shown=excluded.shown, last_shown=excluded.last_shown,
                         next_due=MAX(impressions.next_due, excluded.next_due), title=excluded.title""",
                    writes,
                )
                await db.commit()
        finally:
            await db.close()

    async def react(
        self,
        kind: str,
        tmdb_id: int,
        action: Action,
        *,
        title: Optional[str] = None,
        genres: Optional[list[str]] = None,
        keywords: Optional[list[str]] = None,
        now: Optional[float] = None,
    ) -> None:
        now = now or time.time()
        dismissed = 1 if action == "dismiss" else 0
        due = now + (365 * DAY if dismissed else 2 * DAY)
        db = await self._db()
        try:
            await db.execute(
                """INSERT INTO impressions (kind, tmdb_id, title, engaged, dismissed, last_engaged, next_due, genres, keywords)
                   VALUES (?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(kind, tmdb_id) DO UPDATE SET
                     engaged = impressions.engaged + excluded.engaged,
                     dismissed = MAX(impressions.dismissed, excluded.dismissed),
                     last_engaged = excluded.last_engaged,
                     next_due = excluded.next_due,
                     title = COALESCE(excluded.title, impressions.title),
                     genres = COALESCE(excluded.genres, impressions.genres),
                     keywords = COALESCE(excluded.keywords, impressions.keywords)""",
                (kind, tmdb_id, title, 0 if dismissed else 1, dismissed, now, due,
                 json.dumps(genres) if genres is not None else None,
                 json.dumps(keywords) if keywords is not None else None),
            )
            await db.commit()
        finally:
            await db.close()

    async def state(self, now: Optional[float] = None) -> FeedbackState:
        now = now or time.time()
        out = FeedbackState()
        db = await self._db()
        try:
            async with db.execute("SELECT * FROM impressions") as cur:
                rows = await cur.fetchall()
        finally:
            await db.close()
        for r in rows:
            key = (r["kind"], int(r["tmdb_id"]))
            recently_shown = r["last_shown"] and now - r["last_shown"] < STICKY
            if r["dismissed"] or (r["next_due"] > now and not recently_shown):
                out.hidden.add(key)
            themes = {"kind": r["kind"], "tmdb_id": r["tmdb_id"], "title": r["title"],
                      "genres": json.loads(r["genres"] or "[]"), "keywords": json.loads(r["keywords"] or "[]")}
            if r["dismissed"]:
                out.disliked.append(themes)
            elif r["engaged"]:
                out.liked.append(themes)
        return out
