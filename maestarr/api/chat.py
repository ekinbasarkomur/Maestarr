"""Chat (Vercel AI SDK UI message stream, AI SDK v6) and conversation history.

The browser owns the live history of an open chat and sends it with every
request; the server stores each completed run so a conversation survives
reloads, can be reopened from the sidebar, and is the same object Telegram
writes to.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from maestarr.agent.progress import TURN, TurnRecorder
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
    recorder: Optional[TurnRecorder] = None
    if cid:
        # The user's message is kept even if the turn never finishes, and every
        # step after it is saved as it happens (see maestarr.agent.progress).
        await store.save_messages(cid, history)
        recorder = TurnRecorder(store, cid, history)
        TURN.set(recorder)
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
        recorded as cancelled, keeping what it had done and written so far."""
        try:
            async for chunk in inner:
                if recorder is not None:
                    recorder.partial += text_deltas(chunk)
                    recorder.running += tools_started(chunk)
                yield chunk
        finally:
            if recorder is not None and not finished:
                await asyncio.shield(recorder.cancelled())

    response.body_iterator = guarded()
    return response


def tools_started(chunk: Any) -> list[str]:
    r"""Names of tools whose call started inside one chunk of the UI stream.

    >>> tools_started('data: {"type":"tool-input-start","toolCallId":"a","toolName":"disk_usage"}\n\n')
    ['disk_usage']
    """
    raw = chunk.decode() if isinstance(chunk, (bytes, bytearray)) else str(chunk)
    if "tool-input-start" not in raw:
        return []
    names = []
    for line in raw.splitlines():
        if line.startswith("data: ") and "tool-input-start" in line:
            try:
                event = json.loads(line[6:])
            except ValueError:
                continue
            if event.get("type") == "tool-input-start" and event.get("toolName"):
                names.append(str(event["toolName"]))
    return names


def text_deltas(chunk: Any) -> str:
    r"""The answer text inside one server-sent-events chunk of the UI stream.

    >>> text_deltas(b'data: {"type":"text-delta","id":"t","delta":"Hel"}\n\ndata: {"type":"text-delta","id":"t","delta":"lo"}\n\n')
    'Hello'
    >>> text_deltas('data: {"type":"tool-input-available"}\n\n')
    ''
    """
    raw = chunk.decode() if isinstance(chunk, (bytes, bytearray)) else str(chunk)
    if "text-delta" not in raw:
        return ""
    out = []
    for line in raw.splitlines():
        if line.startswith("data: ") and "text-delta" in line:
            try:
                event = json.loads(line[6:])
            except ValueError:
                continue
            if event.get("type") == "text-delta":
                out.append(str(event.get("delta") or ""))
    return "".join(out)


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
