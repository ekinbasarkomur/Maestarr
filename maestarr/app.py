"""FastAPI application — routers, the MCP endpoint, background workers, and the
built web UI.

Started via `maestarr serve`. Everything the UI needs is under `/api`; MCP
clients use `/mcp` with the instance API key; `/health` is the liveness probe.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.routing import Route

from maestarr import __version__
from maestarr.api import auth, chat, dashboard, settings
from maestarr.config import get_config_store, get_settings, secret
from maestarr.services import get_services, reset_services

logger = logging.getLogger(__name__)

UI_DIST = Path(__file__).resolve().parent / "web"


# --------------------------------------------------------------------------
# Telegram bot supervisor — (re)started whenever its settings change.
# --------------------------------------------------------------------------


class BotSupervisor:
    def __init__(self) -> None:
        self.task: Optional[asyncio.Task[None]] = None
        self.signature: Optional[tuple[str, tuple[int, ...]]] = None

    async def sync(self) -> None:
        s = get_settings()
        token = secret(s.TELEGRAM_BOT_TOKEN) or ""
        wanted = (token, tuple(s.TELEGRAM_ALLOWED_CHAT_IDS)) if token and s.TELEGRAM_ALLOWED_CHAT_IDS else None
        if wanted == self.signature and (self.task is None or not self.task.done()):
            return
        await self.stop()
        self.signature = wanted
        if wanted:
            from maestarr.telegram.bot import run_bot

            self.task = asyncio.create_task(run_bot(get_services(), chat.get_store()), name="telegram-bot")

    async def stop(self) -> None:
        if self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self.task
        self.task = None


bot = BotSupervisor()


async def _after_settings_change() -> None:
    await reset_services()
    await bot.sync()


settings.on_settings_change(_after_settings_change)


# --------------------------------------------------------------------------
# MCP over streamable HTTP at /mcp, behind the instance API key.
# --------------------------------------------------------------------------

_MCP: dict[str, Any] = {}


def _mcp_manager() -> Any:
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

    from maestarr.server import build_server

    _MCP["manager"] = StreamableHTTPSessionManager(app=build_server(), stateless=True, json_response=True)
    return _MCP["manager"]


async def mcp_asgi(scope: Any, receive: Any, send: Any) -> None:
    if scope["type"] == "http":
        token = secret(get_settings().MAESTARR_API_TOKEN)
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        auth_header = headers.get("authorization", "")
        supplied = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else ""
        if not token or not secrets.compare_digest(supplied, token):
            message = "create an API key in Settings → API and send it as a Bearer token"
            await JSONResponse({"error": message}, status_code=401)(scope, receive, send)
            return
    manager = _MCP.get("manager")
    if manager is None:
        await JSONResponse({"error": "MCP not started"}, status_code=503)(scope, receive, send)
        return
    await manager.handle_request(scope, receive, send)


class _McpEndpoint:
    """Callable object so Starlette treats it as a raw ASGI app (no slash redirect)."""

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        await mcp_asgi(scope, receive, send)


# --------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    get_config_store()  # create the database early
    svc = get_services()
    try:
        removed = await svc.resolver.cleanup_stale_probes()
        if removed:
            logger.info("removed %d stale metadata probes", removed)
    except Exception as exc:  # noqa: BLE001 — qBittorrent may simply be down
        logger.debug("probe cleanup skipped: %s", exc)
    await bot.sync()
    manager = _mcp_manager()
    async with manager.run():
        yield
    await bot.stop()
    await reset_services()


app = FastAPI(title="Maestarr", version=__version__, lifespan=lifespan)
app.include_router(auth.router)
app.include_router(settings.router)
app.include_router(chat.router)
app.include_router(dashboard.router)
app.router.routes.append(Route("/mcp", _McpEndpoint(), methods=["GET", "POST", "DELETE"]))
app.mount("/mcp", mcp_asgi)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "version": __version__}


@app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
async def api_not_found(rest: str) -> JSONResponse:
    return JSONResponse({"detail": f"no such endpoint: /api/{rest}"}, status_code=404)


# The built UI (ui/ → maestarr/web). Any non-API path falls back to index.html
# so client-side routes survive a reload.
if (UI_DIST / "index.html").exists():
    if (UI_DIST / "assets").exists():
        app.mount("/assets", StaticFiles(directory=UI_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        candidate = (UI_DIST / path).resolve()
        if path and candidate.is_file() and UI_DIST in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(UI_DIST / "index.html", headers={"Cache-Control": "no-cache"})
