"""The MCP bridge exposes the agent's own toolset."""

from __future__ import annotations

import json

from pydantic import SecretStr

from maestarr.config import get_settings
from maestarr.server import call, list_tool_defs
from maestarr.services import Services


async def test_unconfigured_services_hide_their_tools():
    svc = Services.from_settings(get_settings())
    names = {t.name for t in await list_tool_defs(svc)}
    assert "get_preferences" in names and "search_library" in names
    # Sonarr/qBittorrent/TMDB/Whisparr are not configured in tests.
    assert "series_details" not in names
    assert "list_torrents" not in names
    assert "recommend" not in names
    assert "whisparr_lookup" not in names
    await svc.aclose()


async def test_write_tools_are_marked_destructive():
    svc = Services.from_settings(get_settings())
    tools = {t.name: t for t in await list_tool_defs(svc)}
    assert tools["grab_release"].annotations.destructive_hint is True
    assert tools["get_preferences"].annotations.read_only_hint is True
    await svc.aclose()


async def test_call_runs_a_tool_and_reports_unknown_ones():
    svc = Services.from_settings(get_settings())
    is_error, text = await call(svc, "get_preferences", {})
    assert not is_error and "max_resolution" in json.loads(text)
    is_error, text = await call(svc, "no_such_tool", {})
    assert is_error and "unknown" in text
    await svc.aclose()


async def test_adult_switch_gates_whisparr_and_stashdb():
    base = get_settings().model_copy(
        update={
            "WHISPARR_URL": "http://whisparr:6969",
            "WHISPARR_API_KEY": SecretStr("k"),
            "STASHDB_ENABLED": True,
            "STASHDB_API_KEY": SecretStr("k"),
        }
    )
    off = Services.from_settings(base)
    names = {t.name for t in await list_tool_defs(off)}
    assert off.whisparr is None and off.stashdb is None
    assert "whisparr_lookup" not in names and "adult_search" not in names
    await off.aclose()

    on = Services.from_settings(base.model_copy(update={"MAESTARR_ADULT_CONTENT": True}))
    names = {t.name for t in await list_tool_defs(on)}
    assert "whisparr_lookup" in names and "adult_search" in names
    await on.aclose()
