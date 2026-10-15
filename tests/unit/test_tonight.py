"""Picks for tonight: downloads stay on the shelf unless turned down."""

import time
from types import SimpleNamespace

from maestarr.domain import MediaRef, TasteProfile, WatchEvent
from maestarr.ops import discovery
from maestarr.taste import rows
from maestarr.taste.feedback import FeedbackStore


class FakeTmdb:
    async def to_ref(self, kind, item, anime=False):
        return MediaRef(kind="movie", title=item["title"], tmdb_id=item["id"])


class FakeCache:
    tmdb = FakeTmdb()

    async def details(self, kind, tmdb_id):
        return {"id": tmdb_id, "title": f"Film {tmdb_id}"}


async def test_shown_downloads_stay_and_turned_down_ones_leave(tmp_path, monkeypatch):
    store = FeedbackStore(tmp_path / "f.sqlite3")
    now = time.time()
    await store.shown([("movie", 1, "Film 1"), ("movie", 2, "Film 2")], now=now - 13 * 3600)  # resting
    await store.react("movie", 2, "dismiss", title="Film 2", now=now)
    svc = SimpleNamespace(memo={}, settings=None)
    library = [WatchEvent(kind="movie", title=f"Film {i}", tmdb_id=i, source="library") for i in (1, 2, 3)]

    async def none(*a, **k):
        return set()

    async def profile(*a, **k):
        return TasteProfile()

    async def index(*a, **k):
        return set(), {"movie_by_tmdb": {}, "series_by_tvdb": {}}

    async def history(*a, **k):
        return library

    monkeypatch.setattr(discovery, "taste_profile", profile)
    monkeypatch.setattr(discovery, "watched_set", none)
    monkeypatch.setattr(discovery, "feedback_store", lambda svc: store)
    monkeypatch.setattr(discovery, "library_index", index)
    monkeypatch.setattr(discovery, "library_history", history)
    monkeypatch.setattr(discovery, "_cache", lambda svc: FakeCache())

    ready = await rows.ready_to_watch(svc)  # type: ignore[arg-type]
    assert sorted(r["tmdb_id"] for r in ready) == [1, 3]
    assert all(r["ready"] and r["in_library"] for r in ready)
