"""Authentication for the HTTP API.

Two ways in:
- the web UI's login session (HttpOnly cookie), and
- the instance API key (`Authorization: Bearer <key>`), for MCP clients and
  scripts — generated from Settings → API.

Before the first account exists every protected route answers 401 with
`setup_required`, and only the setup routes work.
"""

from __future__ import annotations

import secrets
from typing import Any, Optional

from fastapi import HTTPException, Request

from maestarr.config import get_config_store, get_settings, secret

SESSION_COOKIE = "maestarr_session"


def bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    return header[7:].strip() if header.lower().startswith("bearer ") else ""


def current_user(request: Request) -> Optional[dict[str, Any]]:
    store = get_config_store()
    token = request.cookies.get(SESSION_COOKIE, "")
    if token:
        user = store.session_user(token)
        if user:
            return user
    api_key = secret(get_settings().MAESTARR_API_TOKEN)
    supplied = bearer(request)
    if api_key and supplied and secrets.compare_digest(supplied, api_key):
        return {"id": 0, "username": "api"}
    return None


async def require_user(request: Request) -> dict[str, Any]:
    user = current_user(request)
    if user:
        return user
    if not get_config_store().has_users():
        raise HTTPException(status_code=401, detail="setup_required")
    raise HTTPException(status_code=401, detail="login_required")


async def require_setup_open(request: Request) -> Optional[dict[str, Any]]:
    """Setup routes: open until the first account exists, then login-only."""
    if not get_config_store().has_users():
        return None
    return await require_user(request)
