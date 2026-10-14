"""Chat (Vercel AI SDK UI message stream, AI SDK v6) and conversation history.

The browser owns the live history of an open chat and sends it with every
request; the server stores each completed run so a conversation survives
reloads, can be reopened from the sidebar, and is the same object Telegram
writes to.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from maestarr.api.deps import require_user
from maestarr.config import get_settings
from maestarr.store import Store, title_from

router = APIRouter(prefix="/api", tags=["chat"])


def get_store() -> Store:
    return Store(get_settings().database_path)


def _first_user_text(body: dict[str, Any]) -> str:
    for message in body.get("messages", []):
        if message.get("role") == "user":
            for part in message.get("parts", []):
                if part.get("type") == "text" and part.get("text"):
                    return str(part["text"])
    return ""


@router.post("/chat")
async def chat(request: Request, _: Any = Depends(require_user)) -> Response:
    from maestarr.agent.agent import get_agent
    from maestarr.api.stream import MaestarrAdapter
    from maestarr.services import get_services

    agent = get_agent()
    if agent.model is None:
        return JSONResponse(
            {"detail": "ai_not_configured", "message": "Add an AI provider in Settings → AI model first."},
            status_code=409,
        )
    raw = await request.body()  # cached by Starlette; the adapter reads it again
    try:
        body = json.loads(raw or b"{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="invalid JSON") from exc
    store = get_store()
    cid = str(body.get("id") or "")
    if cid and await store.get(cid) is None:
        await store.create(conversation_id=cid, title=title_from(_first_user_text(body)))

    adapter = await MaestarrAdapter.from_request(request, agent=agent, sdk_version=6)  # type: ignore[arg-type]
    history = list(adapter.messages)
    if cid:
        # The user's message is kept even if the turn never finishes.
        await store.save_messages(cid, history)
    finished = False

    async def on_complete(result: Any) -> None:
        nonlocal finished
        finished = True
        if cid:
            await store.save_messages(cid, result.all_messages())

    response = adapter.streaming_response(adapter.run_stream(deps=get_services(), on_complete=on_complete))
    inner = response.body_iterator

    async def guarded() -> Any:
        """Stop, a page reload or a closed tab ends the stream early: the turn is
        abandoned and recorded as cancelled."""
        try:
            async for chunk in inner:
                yield chunk
        finally:
            if cid and not finished:
                await asyncio.shield(store.save_messages(cid, mark_cancelled(history)))

    response.body_iterator = guarded()
    return response


CANCELLED = "⏹ Cancelled"


def mark_cancelled(history: list[Any]) -> list[Any]:
    """The history with a cancelled marker as the assistant's answer to the last message.

    >>> from pydantic_ai.messages import ModelRequest, UserPromptPart
    >>> out = mark_cancelled([ModelRequest(parts=[UserPromptPart(content="hi")])])
    >>> out[-1].parts[0].content
    '⏹ Cancelled'
    """
    from pydantic_ai.messages import ModelResponse, TextPart

    if history and isinstance(history[-1], ModelResponse) and any(
        isinstance(p, TextPart) and p.content == CANCELLED for p in history[-1].parts
    ):
        return history
    return [*history, ModelResponse(parts=[TextPart(content=CANCELLED)])]


@router.get("/conversations")
async def list_conversations(_: Any = Depends(require_user)) -> list[dict[str, Any]]:
    return await get_store().list_all(channel=None)


@router.get("/conversations/{cid}")
async def get_conversation(cid: str, _: Any = Depends(require_user)) -> dict[str, Any]:
    from pydantic_ai.ui.vercel_ai import VercelAIAdapter

    store = get_store()
    row = await store.get(cid)
    if row is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    messages = await store.messages(cid)
    ui = VercelAIAdapter.dump_messages(messages, sdk_version=6)
    return {
        "id": cid,
        "title": row["title"],
        "channel": row["channel"],
        "messages": [m.model_dump(mode="json", by_alias=True, exclude_none=True) for m in ui],
    }


class Rename(BaseModel):
    title: str


@router.patch("/conversations/{cid}")
async def rename_conversation(cid: str, body: Rename, _: Any = Depends(require_user)) -> dict[str, str]:
    await get_store().rename(cid, body.title)
    return {"id": cid, "title": body.title}


@router.delete("/conversations/{cid}")
async def delete_conversation(cid: str, _: Any = Depends(require_user)) -> dict[str, str]:
    await get_store().delete(cid)
    return {"deleted": cid}
