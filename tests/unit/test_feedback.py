"""Ignored suggestions come back less and less often; liked ones count; "not for me" hides."""

from __future__ import annotations

from maestarr.taste.feedback import DAY, FeedbackStore


async def test_ignored_titles_are_spaced_out(tmp_path):
    store = FeedbackStore(tmp_path / "f.sqlite3")
    t0 = 1_000_000.0
    await store.shown([("movie", 1, "A")], now=t0)
    assert ("movie", 1) not in (await store.state(now=t0 + 3600)).hidden  # sticky for 12 h
    assert ("movie", 1) in (await store.state(now=t0 + 13 * 3600)).hidden  # then due after 1 day
    assert ("movie", 1) not in (await store.state(now=t0 + 1.1 * DAY)).hidden
    await store.shown([("movie", 1, "A")], now=t0 + 1.1 * DAY)  # ignored again → 2 days
    st = await store.state(now=t0 + 2.5 * DAY)
    assert ("movie", 1) in st.hidden
    assert ("movie", 1) not in (await store.state(now=t0 + 3.2 * DAY)).hidden


async def test_a_repeat_view_within_the_window_does_not_count(tmp_path):
    store = FeedbackStore(tmp_path / "f.sqlite3")
    await store.shown([("tv", 2, "B")], now=0.0 + DAY)
    await store.shown([("tv", 2, "B")], now=DAY + 3600)  # page reload an hour later
    await store.shown([("tv", 2, "B")], now=DAY + 2 * DAY)  # second real impression → 2-day wait
    assert ("tv", 2) in (await store.state(now=DAY + 3.5 * DAY)).hidden


async def test_reactions(tmp_path):
    store = FeedbackStore(tmp_path / "f.sqlite3")
    await store.react("movie", 3, "search", title="C", genres=["Crime"], keywords=["heist"], now=DAY)
    await store.react("movie", 4, "dismiss", title="D", genres=["Horror"], keywords=["gore"], now=DAY)
    st = await store.state(now=DAY + 10 * DAY)
    assert [x["keywords"] for x in st.liked] == [["heist"]]
    assert [x["keywords"] for x in st.disliked] == [["gore"]]
    assert ("movie", 4) in st.hidden and ("movie", 3) not in st.hidden
