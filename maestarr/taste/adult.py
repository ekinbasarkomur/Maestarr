"""Adult discovery: streaming-style shelves and a detailed search over StashDB.

Kept apart from film and series taste on purpose: its own profile (performers,
studios, tags) and its own impressions table, so scenes never shape film picks
and films never shape scenes. Everything here sits behind the 18+ switch.

The profile is built from what the user keeps in Whisparr (downloaded counts
more than only monitored), their StashDB favourites (performers and studios),
the tags of their library scenes, and what they opened or turned down here.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

import aiosqlite

from maestarr.cache import cached
from maestarr.clients.base import ServiceError
from maestarr.ops import discovery
from maestarr.services import Services
from maestarr.taste.feedback import DAY, STICKY, next_interval_days

logger = logging.getLogger(__name__)

W_FILE = 1.0  # a scene downloaded into Whisparr
W_MONITORED = 0.6  # wanted, not downloaded yet
W_LISTED = 0.3  # in Whisparr but unmonitored (e.g. added with a studio or performer)
W_FAVOURITE = 4.0  # a StashDB favourite performer or studio
W_LIKED = 0.8  # opened or fetched from a suggestion
TAG_SCAN = 40  # library scenes whose tags are read
ROW_MAX = 18
ROW_MIN = 4
SKIP_CATEGORIES = {"Orientation", "Production", "Camera", "Audio", "Video", "Meta"}
SORTS = {
    "relevance": ("POPULARITY", "DESC"),
    "popular": ("POPULARITY", "DESC"),
    "trending": ("TRENDING", "DESC"),
    "newest": ("DATE", "DESC"),
    "oldest": ("DATE", "ASC"),
    "longest": ("DURATION", "DESC"),
    "shortest": ("DURATION", "ASC"),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS adult_impressions (
    scene_id TEXT PRIMARY KEY,
    title TEXT,
    shown INTEGER NOT NULL DEFAULT 0,
    engaged INTEGER NOT NULL DEFAULT 0,
    dismissed INTEGER NOT NULL DEFAULT 0,
    last_shown REAL,
    last_engaged REAL,
    next_due REAL NOT NULL DEFAULT 0,
    performers TEXT,
    studio TEXT,
    tags TEXT
);
"""


def gate(svc: Services) -> Any:
    if not svc.settings.MAESTARR_ADULT_CONTENT:
        raise ServiceError("stashdb", "adult content is switched off (Settings → Discovery)")
    if not svc.stashdb:
        raise ServiceError("stashdb", "StashDB is not set up — enable it and add an API key under Settings → Discovery")
    return svc.stashdb


# --- feedback -----------------------------------------------------------------


@dataclass
class AdultFeedback:
    hidden: set[str] = field(default_factory=set)
    liked: list[dict[str, Any]] = field(default_factory=list)
    disliked: list[dict[str, Any]] = field(default_factory=list)


class AdultFeedbackStore:
    """Impressions and reactions for scenes, spaced out like the film picks."""

    def __init__(self, path: Path):
        self.path = path
        self._ready = False

    async def _db(self) -> aiosqlite.Connection:
        db = await aiosqlite.connect(self.path)
        db.row_factory = aiosqlite.Row
        if not self._ready:
            await db.executescript(SCHEMA)
            await db.commit()
            self._ready = True
        return db

    async def shown(self, items: Iterable[tuple[str, str]], now: Optional[float] = None) -> None:
        now = now or time.time()
        db = await self._db()
        try:
            for scene_id, title in items:
                async with db.execute(
                    "SELECT shown, last_shown, last_engaged FROM adult_impressions WHERE scene_id=?", (scene_id,)
                ) as cur:
                    row = await cur.fetchone()
                if row and row["last_shown"] and now - row["last_shown"] < STICKY:
                    continue
                shown = (row["shown"] if row else 0) + 1
                engaged_since = bool(row and row["last_engaged"] and row["last_engaged"] >= (row["last_shown"] or 0))
                due = now + (2 * DAY if engaged_since else next_interval_days(shown) * DAY)
                await db.execute(
                    """INSERT INTO adult_impressions (scene_id, title, shown, last_shown, next_due) VALUES (?,?,?,?,?)
                       ON CONFLICT(scene_id) DO UPDATE SET shown=excluded.shown, last_shown=excluded.last_shown,
                         next_due=MAX(adult_impressions.next_due, excluded.next_due), title=excluded.title""",
                    (scene_id, title, shown, now, due),
                )
            await db.commit()
        finally:
            await db.close()

    async def react(self, scene: dict[str, Any], action: str, now: Optional[float] = None) -> None:
        now = now or time.time()
        dismissed = 1 if action == "dismiss" else 0
        due = now + (365 * DAY if dismissed else 2 * DAY)
        db = await self._db()
        try:
            await db.execute(
                """INSERT INTO adult_impressions
                     (scene_id, title, engaged, dismissed, last_engaged, next_due, performers, studio, tags)
                   VALUES (?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(scene_id) DO UPDATE SET
                     engaged = adult_impressions.engaged + excluded.engaged,
                     dismissed = MAX(adult_impressions.dismissed, excluded.dismissed),
                     last_engaged = excluded.last_engaged, next_due = excluded.next_due,
                     title = COALESCE(excluded.title, adult_impressions.title),
                     performers = COALESCE(excluded.performers, adult_impressions.performers),
                     studio = COALESCE(excluded.studio, adult_impressions.studio),
                     tags = COALESCE(excluded.tags, adult_impressions.tags)""",
                (scene["id"], scene.get("title"), 0 if dismissed else 1, dismissed, now, due,
                 json.dumps(list(zip(scene.get("performer_ids") or [], scene.get("performers") or []))),
                 json.dumps([scene.get("studio_id"), scene.get("studio")]), json.dumps(scene.get("tags") or [])),
            )
            await db.commit()
        finally:
            await db.close()

    async def state(self, now: Optional[float] = None) -> AdultFeedback:
        now = now or time.time()
        out = AdultFeedback()
        db = await self._db()
        try:
            async with db.execute("SELECT * FROM adult_impressions") as cur:
                rows = await cur.fetchall()
        finally:
            await db.close()
        for r in rows:
            recently_shown = r["last_shown"] and now - r["last_shown"] < STICKY
            if r["dismissed"] or (r["next_due"] > now and not recently_shown):
                out.hidden.add(r["scene_id"])
            themes = {"performers": json.loads(r["performers"] or "[]"), "studio": json.loads(r["studio"] or "[null, null]"),
                      "tags": json.loads(r["tags"] or "[]")}
            if r["dismissed"]:
                out.disliked.append(themes)
            elif r["engaged"]:
                out.liked.append(themes)
        return out


def feedback_store(svc: Services) -> AdultFeedbackStore:
    key = "adult_feedback_store"
    if key not in svc.memo:
        svc.memo[key] = AdultFeedbackStore(svc.settings.database_path)
    store: AdultFeedbackStore = svc.memo[key]
    return store


async def record_impressions(svc: Services, scenes: list[dict[str, Any]]) -> None:
    rows = [(s["stash_id"], str(s.get("title") or "")) for s in scenes if s.get("stash_id")]
    if rows:
        try:
            await feedback_store(svc).shown(rows)
        except Exception:  # noqa: BLE001 — bookkeeping must never break a page
            logger.exception("could not record adult impressions")


async def react(svc: Services, scene_id: str, action: str) -> dict[str, Any]:
    stash = gate(svc)
    scene = await stash.scene(scene_id) or {"id": scene_id}
    await feedback_store(svc).react(scene, action)
    return {"ok": True, "stash_id": scene_id, "action": action}


# --- profile ------------------------------------------------------------------


async def _build_profile(svc: Services) -> dict[str, Any]:
    stash = gate(svc)
    library = await svc.whisparr.movies() if svc.whisparr else []
    performers: dict[str, list[Any]] = {}  # id -> [name, weight, gender]
    studios: dict[str, list[Any]] = {}  # id -> [name, weight]
    owned: list[str] = []
    for m in library:
        sid = str(m.get("stashId") or m.get("foreignId") or "")
        if sid:
            owned.append(sid)
        w = W_FILE if m.get("hasFile") else (W_MONITORED if m.get("monitored") else W_LISTED)
        if m.get("studioForeignId"):
            entry = studios.setdefault(m["studioForeignId"], [m.get("studioTitle") or "?", 0.0])
            entry[1] += w
        for pid, name in zip(m.get("performerForeignIds") or [], m.get("performerNames") or []):
            entry = performers.setdefault(pid, [name, 0.0, ""])
            entry[1] += w

    fav_p, fav_s = await asyncio.gather(_safe(stash.favorite_performers()), _safe(stash.favorite_studios()))
    for p in fav_p:
        entry = performers.setdefault(p["id"], [p["name"], 0.0, p.get("gender") or ""])
        entry[1] += W_FAVOURITE
        entry[2] = p.get("gender") or entry[2]
    for st in fav_s:
        studios.setdefault(st["id"], [st["name"], 0.0])[1] += W_FAVOURITE

    # Genders for the most frequent library performers (to follow the women first).
    top = sorted((pid for pid, v in performers.items() if not v[2]), key=lambda pid: -performers[pid][1])[:40]
    if top:
        genders = await _safe_dict(stash.performer_genders(top))
        for pid, g in genders.items():
            performers[pid][2] = g

    # Tags of the scenes the user cares about most: downloaded, then wanted, newest first.
    recent = sorted(library, key=lambda m: (bool(m.get("hasFile")), bool(m.get("monitored")), str(m.get("added") or "")),
                    reverse=True)
    ids = [str(m.get("stashId") or m.get("foreignId")) for m in recent[:TAG_SCAN]]
    batches = await asyncio.gather(*(_safe(stash.scenes_by_ids(ids[i:i + 20])) for i in range(0, len(ids), 20)))
    tag_count: Counter[str] = Counter()
    scanned = 0
    for batch in batches:
        for sc in batch:
            scanned += 1
            tag_count.update(set(sc.get("tags") or []))
    # A tag on most of the library says nothing about taste.
    tags = {t: float(n) for t, n in tag_count.items() if scanned < 5 or n <= 0.6 * scanned}
    # Shelves and quick filters use what happens in a scene, not how people look.
    top = [t for t, _ in sorted(tags.items(), key=lambda kv: -kv[1])[:30]]
    cats = await _safe_cats(stash.tag_categories(top))
    themes = [t for t in top if cats.get(t, ("", ""))[1] != "PEOPLE" and cats.get(t, ("", ""))[0] not in SKIP_CATEGORIES]
    return {
        "performers": performers, "studios": studios, "tags": tags, "themes": themes, "owned": owned,
        "favourite_performers": [p["id"] for p in fav_p], "favourite_studios": [s["id"] for s in fav_s],
    }


async def _safe(coro: Any) -> list[dict[str, Any]]:
    try:
        result: list[dict[str, Any]] = await coro
        return result
    except ServiceError as exc:
        logger.info("stashdb: %s", exc)
        return []


async def _safe_cats(coro: Any) -> dict[str, tuple[str, str]]:
    try:
        result: dict[str, tuple[str, str]] = await coro
        return result
    except ServiceError as exc:
        logger.info("stashdb: %s", exc)
        return {}


async def _safe_dict(coro: Any) -> dict[str, str]:
    try:
        result: dict[str, str] = await coro
        return result
    except ServiceError as exc:
        logger.info("stashdb: %s", exc)
        return {}


async def profile(svc: Services) -> dict[str, Any]:
    """The adult taste profile (cached like watch history), with feedback applied."""
    base = await cached(discovery.cache_store(svc), "data:adult_profile", max_age=discovery.data_age(svc),
                        build=lambda: _build_profile(svc))
    prof = json.loads(json.dumps(base))  # a copy: feedback must not leak into the cache
    fb = await feedback_store(svc).state()
    avoid: Counter[str] = Counter()
    for liked in fb.liked:
        for pid, name in liked["performers"]:
            prof["performers"].setdefault(pid, [name, 0.0, ""])[1] += W_LIKED
        sid, sname = liked["studio"]
        if sid:
            prof["studios"].setdefault(sid, [sname, 0.0])[1] += W_LIKED
        for t in liked["tags"]:
            prof["tags"][t] = prof["tags"].get(t, 0.0) + W_LIKED
    for disliked in fb.disliked:
        avoid.update(disliked["tags"])
        sid, _ = disliked["studio"]
        if sid:
            avoid[f"studio:{sid}"] += 2
    prof["avoid"] = dict(avoid)
    prof["hidden"] = sorted(fb.hidden)
    return prof


def score(scene: dict[str, Any], prof: dict[str, Any]) -> tuple[float, list[str]]:
    """How well a scene fits: performers 45 %, studio 30 %, tags 25 %, minus avoided themes."""
    perfs = prof["performers"]
    studios = prof["studios"]
    tags = prof["tags"]
    top_p = max((v[1] for v in perfs.values()), default=1.0) or 1.0
    top_s = max((v[1] for v in studios.values()), default=1.0) or 1.0
    top_t = max(tags.values(), default=1.0) or 1.0
    # Strongest match first, women before men when naming the reason.
    matched = sorted(((perfs[p][2] == "FEMALE", perfs[p][1], perfs[p][0]) for p in scene.get("performer_ids", [])
                      if p in perfs), reverse=True)
    # Men recur across a library without saying much about taste: they count less.
    p_score = max(m[1] * (1.0 if m[0] or not perfs_gendered(perfs) else 0.35) for m in matched) / top_p if matched else 0.0
    st = studios.get(scene.get("studio_id") or "")
    s_score = st[1] / top_s if st else 0.0
    shared = [t for t in scene.get("tags", []) if t in tags]
    t_score = min(1.0, sum(tags[t] for t in shared) / (top_t * 3)) if shared else 0.0
    value = 0.45 * p_score + 0.3 * s_score + 0.25 * t_score
    avoid = prof.get("avoid") or {}
    penalty = sum(avoid.get(t, 0) for t in scene.get("tags", [])) + avoid.get(f"studio:{scene.get('studio_id')}", 0)
    value -= min(0.5, 0.1 * penalty)
    why: list[str] = []
    favs = set(prof.get("favourite_performers") or [])
    fav_hit = [perfs[p][0] for p in scene.get("performer_ids", []) if p in favs]
    if fav_hit:
        why.append(f"With {fav_hit[0]}, one of your favourites" if len(fav_hit) == 1
                   else f"With {fav_hit[0]} and {fav_hit[1]}, both favourites of yours")
    elif matched and matched[0][0]:
        why.append(f"With {matched[0][2]}, who you watch a lot")
    if st:
        why.append(f"From {st[0]}" + (", a favourite studio" if scene.get("studio_id") in set(prof.get("favourite_studios") or []) else ""))
    themes = set(prof.get("themes") or [])
    named = [t for t in shared if t in themes] if themes else shared
    if named and len(why) < 2:
        why.append("Tagged " + ", ".join(sorted(named, key=lambda t: -tags[t])[:3]))
    return value, why


def perfs_gendered(perfs: dict[str, list[Any]]) -> bool:
    return any(v[2] for v in perfs.values())


def _out(scene: dict[str, Any], why: list[str], owned: set[str]) -> dict[str, Any]:
    return {**scene, "kind": "scene", "stash_id": scene["id"], "why": why, "in_library": scene["id"] in owned}


# --- shelves ------------------------------------------------------------------


async def rows(svc: Services, *, refresh: bool = False) -> dict[str, Any]:
    """The adult shelves, cached for the picks interval; turned-down scenes leave at once."""
    gate(svc)
    store = discovery.cache_store(svc)
    if refresh:
        await store.drop("picks:adult")
        await store.drop("data:adult")
    out = await cached(store, "picks:adult_rows", max_age=discovery.picks_age(svc), build=lambda: _build_rows(svc))
    hidden = (await feedback_store(svc).state()).hidden
    shelves = []
    for row in out["rows"]:
        items = [i for i in row["items"] if i["stash_id"] not in hidden]
        if len(items) >= ROW_MIN:
            shelves.append({**row, "items": items})
    return {**out, "rows": shelves}


async def _build_rows(svc: Services) -> dict[str, Any]:
    stash = gate(svc)
    prof = await profile(svc)
    owned = set(prof["owned"])
    skip = owned | set(prof["hidden"])
    perfs = prof["performers"]
    studios = prof["studios"]

    # Follow the women first: libraries repeat the same few male performers.
    ranked = sorted(perfs, key=lambda p: -perfs[p][1])
    women = [p for p in ranked if perfs[p][2] == "FEMALE"]
    people = (women if len(women) >= 3 else women + [p for p in ranked if p not in women])[:4]
    top_studios = sorted(studios, key=lambda s: -studios[s][1])[:3]
    top_tags = (prof.get("themes") or [])[:2]
    tag_ids = await asyncio.gather(*(_tag(stash, t) for t in top_tags))
    has_favs = bool(prof["favourite_performers"] or prof["favourite_studios"])

    jobs: list[tuple[str, str, Optional[str], Any]] = []  # (row id, title, subtitle, query)
    if has_favs:
        jobs.append(("favourites", "New from your favourites", "Performers and studios you follow on StashDB",
                     stash.query_scenes(favorites="ALL", sort="DATE", per_page=40)))
    for pid in people:
        jobs.append((f"performer-{pid}", f"More with {perfs[pid][0]}", None,
                     stash.query_scenes(performers=[pid], sort="POPULARITY", per_page=30)))
    for sid in top_studios:
        jobs.append((f"studio-{sid}", f"New from {studios[sid][0]}", None,
                     stash.query_scenes(studios=[sid], sort="DATE", per_page=30)))
    for tag, tid in zip(top_tags, tag_ids):
        if tid:
            jobs.append((f"tag-{tid}", f"{tag} picks", "A theme in your library",
                         stash.query_scenes(tags=[tid], sort="POPULARITY", per_page=40)))
    jobs.append(("trending", "Trending on StashDB", "Popular this week",
                 stash.query_scenes(sort="TRENDING", per_page=40)))
    results = await asyncio.gather(*(_safe(j[3]) for j in jobs))

    pool: dict[str, dict[str, Any]] = {}
    for batch in results:
        for sc in batch:
            if sc["id"] not in skip:
                pool.setdefault(sc["id"], sc)
    scored = {sid: score(sc, prof) for sid, sc in pool.items()}
    used: set[str] = set()
    shelves: list[dict[str, Any]] = []

    picks = sorted((sid for sid in pool if scored[sid][0] > 0), key=lambda sid: -scored[sid][0])[:ROW_MAX]
    if len(picks) >= ROW_MIN:
        used.update(picks)
        shelves.append({"id": "picks", "title": "Top picks for you", "subtitle": None,
                        "items": [_out(pool[s], scored[s][1] or ["Similar to your library"], owned) for s in picks]})
    for (row_id, title, subtitle, _), batch in zip(jobs, results):
        items = []
        for sc in batch:
            if sc["id"] in skip or sc["id"] in used:
                continue
            why = scored.get(sc["id"], (0.0, []))[1]
            items.append(_out(sc, why or [subtitle or title], owned))
            used.add(sc["id"])
            if len(items) >= ROW_MAX:
                break
        if len(items) >= ROW_MIN:
            shelves.append({"id": row_id, "title": title, "subtitle": subtitle, "items": items})
        else:
            used.difference_update(i["stash_id"] for i in items)

    based_on = [perfs[p][0] for p in people[:3]] + [studios[s][0] for s in top_studios[:2]]
    return {"rows": shelves, "based_on": based_on, "tags": (prof.get("themes") or [])[:14]}


async def _tag(stash: Any, name: str) -> Optional[str]:
    try:
        found = await stash.tag_id(name)
    except ServiceError:
        return None
    return found["id"] if found else None


# --- search -------------------------------------------------------------------


async def search(
    svc: Services,
    *,
    text: Optional[str] = None,
    tags: Optional[list[str]] = None,
    exclude_tags: Optional[list[str]] = None,
    performers: Optional[list[str]] = None,
    studios: Optional[list[str]] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    min_minutes: Optional[int] = None,
    max_minutes: Optional[int] = None,
    sort: str = "relevance",
    limit: int = 30,
) -> dict[str, Any]:
    """Scenes by text, tags (all must match; excluded ones must not), performers and
    studios (any), release dates and length. Names are matched on StashDB."""
    stash = gate(svc)
    tags, exclude_tags, performers, studios = tags or [], exclude_tags or [], performers or [], studios or []
    tag_hits = await asyncio.gather(*(_tag(stash, t) for t in tags + exclude_tags))
    inc_ids = [t for t in tag_hits[: len(tags)] if t]
    exc_ids = [t for t in tag_hits[len(tags):] if t]
    perf_hits = [_best(n, h) for n, h in zip(performers, await asyncio.gather(
        *(_safe(stash.search_performers(p, limit=5)) for p in performers)))]
    studio_hits = [_best(n, h) for n, h in zip(studios, await asyncio.gather(
        *(_safe(stash.search_studios(s, limit=8)) for s in studios)))]
    perf_ids = [h[0]["id"] for h in perf_hits if h]
    studio_ids = [h[0]["id"] for h in studio_hits if h]
    missing = [n for n, t in zip(tags, tag_hits[: len(tags)]) if not t] + [p for p, h in zip(performers, perf_hits) if not h] \
        + [s for s, h in zip(studios, studio_hits) if not h]
    if missing and not (inc_ids or perf_ids or studio_ids or text):
        raise ServiceError("stashdb", f"nothing on StashDB called {', '.join(missing)}")

    filtered_later = bool(min_minutes or max_minutes or (date_from and date_to) or (inc_ids and exc_ids))
    per_page = min(100, limit * 3 if filtered_later else limit)
    only_text = text and not (inc_ids or exc_ids or perf_ids or studio_ids or date_from or date_to)
    if only_text and sort == "relevance":
        scenes = await stash.search_scenes(text, limit=per_page)
    else:
        sort_by, direction = SORTS.get(sort, SORTS["relevance"])
        scenes = await stash.query_scenes(
            text=text or None, tags=inc_ids or None, exclude_tags=exc_ids or None,
            performers=perf_ids or None, studios=studio_ids or None,
            date_from=date_from or None, date_to=date_to or None,
            sort=sort_by, direction=direction, per_page=per_page,
        )

    excluded = {t.lower() for t in exclude_tags}
    prof = await profile(svc)
    owned = set(prof["owned"])
    out = []
    for sc in scenes:
        minutes = sc.get("minutes") or 0
        if min_minutes and minutes < min_minutes:
            continue
        if max_minutes and minutes and minutes > max_minutes:
            continue
        if date_to and sc.get("date") and sc["date"] > date_to:
            continue
        if excluded & {t.lower() for t in sc.get("tags") or []}:
            continue
        why = score(sc, prof)[1]
        out.append(_out(sc, why or ["Matches your search"], owned))
        if len(out) >= limit:
            break
    applied = {"tags": tags, "exclude_tags": exclude_tags, "performers": performers, "studios": studios}
    return {"scenes": out, "applied": {k: v for k, v in applied.items() if v}, "not_found": missing}


def _best(name: str, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The exact-name hit first (searches rank loosely: "Bound Gangbangs" → "Bound Heat")."""
    exact = [h for h in hits if (h.get("name") or "").lower() == name.lower()]
    return exact[:1] or hits[:1]


async def suggest(svc: Services, what: str, q: str, limit: int = 10) -> list[dict[str, Any]]:
    """Autocomplete for the search filters."""
    stash = gate(svc)
    if what == "performer":
        hits = await stash.search_performers(q, limit=limit)
        return [{"id": h["id"], "name": h["name"],
                 "known_for": [x for x in [h.get("disambiguation"), h.get("country")] if x]} for h in hits]
    if what == "studio":
        return [{"id": h["id"], "name": h["name"]} for h in await stash.search_studios(q, limit=limit)]
    hits = await stash.search_tags(q, limit=limit)
    exact = [h for h in hits if h["name"].lower() == q.lower()]
    return [{"id": h["id"], "name": h["name"]} for h in exact + [h for h in hits if h not in exact]]
