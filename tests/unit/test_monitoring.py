"""Monitoring on/off and removal go to the right *arr endpoints, without deleting files."""

from __future__ import annotations

import json

import httpx
import respx
from pydantic import SecretStr

from maestarr.config import get_settings
from maestarr.ops.library import remove_from_library, set_monitored
from maestarr.services import Services

W, S = "http://whisparr:6969", "http://sonarr:8989"


def services() -> Services:
    return Services.from_settings(get_settings().model_copy(update={
        "MAESTARR_ADULT_CONTENT": True, "WHISPARR_URL": W, "WHISPARR_API_KEY": SecretStr("k"),
        "SONARR_URL": S, "SONARR_API_KEY": SecretStr("k"),
    }))


@respx.mock
async def test_unmonitor_a_whisparr_scene_without_touching_files():
    editor = respx.put(f"{W}/api/v3/movie/editor").mock(return_value=httpx.Response(202))
    respx.get(f"{W}/api/v3/movie/171").mock(return_value=httpx.Response(200, json={"id": 171, "title": "Scene", "year": 2020}))
    svc = services()
    out = await set_monitored(svc, app="whisparr", item_id=171, monitored=False)
    assert json.loads(editor.calls.last.request.content) == {"movieIds": [171], "monitored": False}
    assert out["monitored"] is False and out["title"] == "Scene (2020)"
    await svc.aclose()


@respx.mock
async def test_unmonitor_one_season():
    respx.get(f"{S}/api/v3/series/3").mock(return_value=httpx.Response(200, json={
        "id": 3, "title": "Show", "seasons": [{"seasonNumber": 1, "monitored": True}, {"seasonNumber": 2, "monitored": True}]}))
    put = respx.put(f"{S}/api/v3/series/3").mock(return_value=httpx.Response(202))
    svc = services()
    await set_monitored(svc, app="sonarr", item_id=3, monitored=False, season=2)
    sent = json.loads(put.calls.last.request.content)
    assert [s["monitored"] for s in sent["seasons"]] == [True, False]
    await svc.aclose()


@respx.mock
async def test_remove_keeps_files_by_default():
    respx.get(f"{W}/api/v3/movie/171").mock(return_value=httpx.Response(200, json={"id": 171, "title": "Scene"}))
    delete = respx.delete(f"{W}/api/v3/movie/171").mock(return_value=httpx.Response(200))
    svc = services()
    out = await remove_from_library(svc, app="whisparr", item_id=171)
    params = delete.calls.last.request.url.params
    assert params["deleteFiles"] == "false" and params["addImportExclusion"] == "false" and out["removed"]
    await svc.aclose()
