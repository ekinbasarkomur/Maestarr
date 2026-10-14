"""HTTP API: onboarding, auth, settings, chat guard."""

from __future__ import annotations

import httpx
import pytest

from maestarr.app import app


@pytest.fixture
async def client():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _setup(client: httpx.AsyncClient) -> None:
    r = await client.post("/api/auth/setup-account", json={"username": "owner", "password": "longpassword"})
    assert r.status_code == 200, r.text


async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


async def test_fresh_install_requires_setup(client):
    state = (await client.get("/api/auth/state")).json()
    assert state["has_account"] is False and state["setup_complete"] is False and state["user"] is None
    r = await client.get("/api/status")
    assert r.status_code == 401 and r.json()["detail"] == "setup_required"
    # Settings are open during setup (the wizard writes them).
    assert (await client.get("/api/settings")).status_code == 200


async def test_setup_account_logs_in_and_only_works_once(client):
    await _setup(client)
    assert (await client.get("/api/auth/state")).json()["user"]["username"] == "owner"
    assert (await client.get("/api/status")).status_code == 200
    r = await client.post("/api/auth/setup-account", json={"username": "x", "password": "longpassword"})
    assert r.status_code == 409


async def test_short_password_is_rejected(client):
    r = await client.post("/api/auth/setup-account", json={"username": "owner", "password": "short"})
    assert r.status_code == 422


async def test_login_logout(client):
    await _setup(client)
    await client.post("/api/auth/logout")
    assert (await client.get("/api/status")).json()["detail"] == "login_required"
    bad = await client.post("/api/auth/login", json={"username": "owner", "password": "wrongpassword"})
    assert bad.status_code == 401
    ok = await client.post("/api/auth/login", json={"username": "OWNER", "password": "longpassword"})
    assert ok.status_code == 200
    assert (await client.get("/api/status")).status_code == 200


async def test_settings_mask_secrets_and_keep_them(client):
    await _setup(client)
    r = await client.put(
        "/api/settings",
        json={"fields": {"SONARR_URL": "http://sonarr:8989/", "SONARR_API_KEY": "abc123", "SONARR_QUALITY_PROFILE": "HD"}},
    )
    assert r.status_code == 200, r.text
    sonarr = r.json()["sections"]["sonarr"]
    assert sonarr["SONARR_URL"] == "http://sonarr:8989"  # trailing slash trimmed
    assert sonarr["SONARR_API_KEY"] == {"set": True}
    assert "abc123" not in r.text
    # An empty secret box means "keep"; null clears.
    r = await client.put("/api/settings", json={"fields": {"SONARR_API_KEY": ""}})
    assert r.json()["sections"]["sonarr"]["SONARR_API_KEY"] == {"set": True}
    r = await client.put("/api/settings", json={"fields": {"SONARR_API_KEY": None}})
    assert r.json()["sections"]["sonarr"]["SONARR_API_KEY"] == {"set": False}


async def test_settings_reject_unknown_and_bootstrap_fields(client):
    await _setup(client)
    assert (await client.put("/api/settings", json={"fields": {"NOPE": 1}})).status_code == 422
    assert (await client.put("/api/settings", json={"fields": {"MAESTARR_PORT": 1}})).status_code == 422
    r = await client.put("/api/settings", json={"fields": {"MAESTARR_ENRICH_TOP_N": "not a number"}})
    assert r.status_code == 422


async def test_connection_test_reports_missing_fields(client):
    await _setup(client)
    r = await client.post("/api/settings/test/radarr", json={"fields": {}})
    assert r.status_code == 200 and r.json()["ok"] is False
    r = await client.post(
        "/api/settings/test/radarr", json={"fields": {"RADARR_URL": "http://127.0.0.1:9", "RADARR_API_KEY": "k"}}
    )
    assert r.json()["ok"] is False and r.json()["detail"]


async def test_api_token_gives_bearer_access(client):
    await _setup(client)
    token = (await client.post("/api/settings/api-token")).json()["token"]
    assert token.startswith("mae_")
    await client.post("/api/auth/logout")
    assert (await client.get("/api/status")).status_code == 401
    r = await client.get("/api/status", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


async def test_chat_explains_missing_ai_provider(client):
    await _setup(client)
    r = await client.post("/api/chat", json={"id": "c1", "messages": []})
    assert r.status_code == 409 and r.json()["detail"] == "ai_not_configured"


async def test_complete_setup(client):
    await _setup(client)
    assert (await client.post("/api/settings/complete-setup")).json()["setup_complete"] is True
    assert (await client.get("/api/auth/state")).json()["setup_complete"] is True


async def test_unknown_api_path_is_json_404(client):
    r = await client.get("/api/does-not-exist")
    assert r.status_code == 404 and "no such endpoint" in r.json()["detail"]
