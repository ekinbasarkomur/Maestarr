"""Accounts and sessions."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from maestarr import __version__
from maestarr.api.deps import SESSION_COOKIE, current_user, require_user
from maestarr.config import get_config_store, get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=256)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=256)


def _set_cookie(request: Request, response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=30 * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        path="/",
    )


@router.get("/state")
async def state(request: Request) -> dict[str, Any]:
    """What the UI should show first: setup, login, or the app."""
    store = get_config_store()
    user = current_user(request)
    return {
        "version": __version__,
        "has_account": store.has_users(),
        "setup_complete": get_settings().MAESTARR_SETUP_COMPLETE,
        "user": user,
    }


@router.post("/setup-account")
async def setup_account(body: Credentials, request: Request, response: Response) -> dict[str, Any]:
    """Create the first (owner) account. Only possible once."""
    store = get_config_store()
    if store.has_users():
        raise HTTPException(status_code=409, detail="an account already exists")
    try:
        user_id = store.create_user(body.username, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _set_cookie(request, response, store.create_session(user_id))
    return {"user": {"id": user_id, "username": body.username}}


@router.post("/login")
async def login(body: Credentials, request: Request, response: Response) -> dict[str, Any]:
    store = get_config_store()
    user = store.verify_user(body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="wrong username or password")
    _set_cookie(request, response, store.create_session(user["id"]))
    return {"user": user}


@router.post("/logout")
async def logout(request: Request, response: Response) -> dict[str, bool]:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        get_config_store().delete_session(token)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.post("/password")
async def change_password(body: PasswordChange, user: dict = Depends(require_user)) -> dict[str, bool]:
    store = get_config_store()
    if not user.get("id") or not store.verify_user(user["username"], body.current_password):
        raise HTTPException(status_code=401, detail="current password is wrong")
    store.set_password(user["id"], body.new_password)
    return {"ok": True}
