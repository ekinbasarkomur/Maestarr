"""Pairing picks the newest recent /start and ignores everything else."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from maestarr.api.settings import find_start


def update(text: str, ts: float, chat_id: int = 1) -> SimpleNamespace:
    msg = SimpleNamespace(text=text, date=datetime.fromtimestamp(ts, timezone.utc), chat=SimpleNamespace(id=chat_id))
    return SimpleNamespace(message=msg)


def test_newest_recent_start_wins():
    ups = [update("/start", 1000, 1), update("hello", 1500, 2), update("/start", 1600, 3)]
    assert find_start(ups, since=900).chat.id == 3


def test_old_starts_and_other_messages_are_ignored():
    assert find_start([update("/start", 100), update("hi", 2000)], since=1000) is None
    assert find_start([SimpleNamespace(message=None)], since=0) is None
