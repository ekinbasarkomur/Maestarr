"""With 18+ off, adult downloads are invisible to Maestarr."""

from __future__ import annotations

from pydantic import SecretStr

from maestarr.config import get_settings
from maestarr.ops.downloads import visible_torrents
from maestarr.services import Services

ITEMS = [{"hash": "a", "category": "tv"}, {"hash": "b", "category": "adult"}, {"hash": "c", "category": "Whisparr"}]


async def test_adult_categories_are_hidden_while_switched_off():
    svc = Services.from_settings(get_settings())
    assert [t["hash"] for t in await visible_torrents(svc, ITEMS)] == ["a"]
    await svc.aclose()


async def test_everything_shows_while_switched_on():
    s = get_settings().model_copy(update={"MAESTARR_ADULT_CONTENT": True, "WHISPARR_URL": None, "WHISPARR_API_KEY": SecretStr("")})
    svc = Services.from_settings(s)
    assert len(await visible_torrents(svc, ITEMS)) == 3
    await svc.aclose()
