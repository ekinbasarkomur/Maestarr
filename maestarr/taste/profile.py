"""Watch history → weighted taste profile.

Weighting (after Curatarr's well-tested scheme, independently implemented):
each watched title counts `recency × rating × rewatch`, where

- recency: 0-30 days 1.0, ≤90 0.75, ≤180 0.5, ≤365 0.25, older 0.1,
- rating (0-10): ≥9 1.0, ≥7 0.75, ≥5 0.5, lower 0.25, unrated 0.6,
- rewatch: log2(plays) + 1.

Its genres, keywords, people, language and decade feed weighted counters,
normalised so the strongest entry of each dimension is 1.0.
"""

from __future__ import annotations

import asyncio
import logging
import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

from maestarr.clients.base import ServiceError
from maestarr.clients.tmdb import TmdbClient, credits_people, tmdb_kind
from maestarr.domain import MediaRef, TasteProfile, WatchEvent

logger = logging.getLogger(__name__)


def recency_weight(watched_at: Optional[datetime], now: Optional[datetime] = None) -> float:
    """
    >>> from datetime import timedelta
    >>> now = datetime(2026, 10, 14, tzinfo=timezone.utc)
    >>> [recency_weight(now - timedelta(days=d), now) for d in (3, 60, 120, 300, 900)]
    [1.0, 0.75, 0.5, 0.25, 0.1]
    >>> recency_weight(None)
    0.25
    """
    if watched_at is None:
        return 0.25
    now = now or datetime.now(timezone.utc)
    days = (now - watched_at).days
    for limit, weight in ((30, 1.0), (90, 0.75), (180, 0.5), (365, 0.25)):
        if days <= limit:
            return weight
    return 0.1


def rating_weight(rating: Optional[float]) -> float:
    """
    >>> [rating_weight(r) for r in (9.5, 7, 5.5, 3, None)]
    [1.0, 0.75, 0.5, 0.25, 0.6]
    """
    if rating is None:
        return 0.6
    if rating >= 9:
        return 1.0
    if rating >= 7:
        return 0.75
    if rating >= 5:
        return 0.5
    return 0.25


def event_weight(ev: WatchEvent, now: Optional[datetime] = None) -> float:
    return recency_weight(ev.watched_at, now) * rating_weight(ev.rating) * (math.log2(max(1, ev.play_count)) + 1)


def merge_history(*sources: list[WatchEvent]) -> list[WatchEvent]:
    """De-duplicate across sources by id (falling back to title+year).

    >>> a = WatchEvent(kind="movie", title="X", year=2000, tmdb_id=1, play_count=1, rating=None)
    >>> b = WatchEvent(kind="movie", title="X", year=2000, tmdb_id=1, play_count=2, rating=8, source="trakt")
    >>> [(e.play_count, e.rating) for e in merge_history([a], [b])]
    [(2, 8.0)]
    """
    merged: dict[str, WatchEvent] = {}
    for source in sources:
        for ev in source:
            key = (
                f"tmdb:{ev.tmdb_id}" if ev.tmdb_id
                else f"imdb:{ev.imdb_id}" if ev.imdb_id
                else f"tvdb:{ev.tvdb_id}" if ev.tvdb_id
                else f"t:{ev.title.lower()}:{ev.year}"
            )
            if key not in merged:
                merged[key] = ev.model_copy()
                continue
            cur = merged[key]
            cur.play_count = max(cur.play_count, ev.play_count)
            cur.rating = cur.rating if cur.rating is not None else ev.rating
            if ev.watched_at and (cur.watched_at is None or ev.watched_at > cur.watched_at):
                cur.watched_at = ev.watched_at
    return list(merged.values())


class DetailsCache:
    """TMDB details with id resolution (imdb/tvdb/title → tmdb), memoised."""

    def __init__(self, tmdb: TmdbClient, memo: dict[str, Any]):
        self.tmdb = tmdb
        self.memo = memo
        self._sem = asyncio.Semaphore(8)

    async def details(self, kind: str, tmdb_id: int) -> Optional[dict[str, Any]]:
        key = f"tmdb:{kind}:{tmdb_id}"
        if key in self.memo:
            return self.memo[key]
        async with self._sem:
            try:
                data = await self.tmdb.details(kind, tmdb_id)  # type: ignore[arg-type]
            except ServiceError as exc:
                logger.debug("tmdb details %s failed: %s", key, exc)
                data = None
        self.memo[key] = data
        return data

    async def resolve(self, ev: WatchEvent) -> Optional[tuple[str, int]]:
        kind = tmdb_kind(ev.kind)
        if ev.tmdb_id:
            return kind, ev.tmdb_id
        try:
            if ev.imdb_id:
                found = await self.tmdb.find(ev.imdb_id, "imdb_id")
                hits = found.get("movie_results" if kind == "movie" else "tv_results") or []
                if hits:
                    return kind, hits[0]["id"]
            if ev.tvdb_id and kind == "tv":
                found = await self.tmdb.find(str(ev.tvdb_id), "tvdb_id")
                if found.get("tv_results"):
                    return kind, found["tv_results"][0]["id"]
            hits = await self.tmdb.search(kind, ev.title, ev.year)
            if hits:
                return kind, hits[0]["id"]
        except ServiceError:
            return None
        return None


async def build_profile(history: list[WatchEvent], cache: DetailsCache, *, max_items: int = 80) -> TasteProfile:
    now = datetime.now(timezone.utc)
    ranked = sorted(history, key=lambda e: -event_weight(e, now))[:max_items]
    resolved = await asyncio.gather(*(cache.resolve(ev) for ev in ranked))
    details = await asyncio.gather(*(cache.details(*r) if r else _none() for r in resolved))

    dims: dict[str, dict[str, float]] = {d: defaultdict(float) for d in ("genres", "keywords", "people", "languages", "decades")}
    seeds: list[tuple[float, MediaRef]] = []
    for ev, res, det in zip(ranked, resolved, details):
        if not res or not det:
            continue
        w = event_weight(ev, now)
        kind, _ = res
        ref = await cache.tmdb.to_ref(kind, det, anime=ev.kind == "anime")  # type: ignore[arg-type]
        for g in ref.genres:
            dims["genres"][g] += w
        for k in ref.keywords:
            dims["keywords"][k] += w
        for p in credits_people(det):
            dims["people"][p] += w
        if ref.original_language:
            dims["languages"][ref.original_language] += w
        if ref.year:
            dims["decades"][f"{ref.year // 10 * 10}s"] += w
        ref.watched = True
        seeds.append((w, ref))

    def norm(d: dict[str, float], keep: int) -> dict[str, float]:
        if not d:
            return {}
        top = max(d.values())
        return {k: round(v / top, 3) for k, v in sorted(d.items(), key=lambda kv: -kv[1])[:keep]}

    return TasteProfile(
        genres=norm(dims["genres"], 30),
        keywords=norm(dims["keywords"], 150),
        people=norm(dims["people"], 100),
        languages=norm(dims["languages"], 15),
        decades=norm(dims["decades"], 12),
        seeds=[ref for _, ref in sorted(seeds, key=lambda s: -s[0])[:12]],
        history_size=len(history),
    )


async def _none() -> None:
    return None
