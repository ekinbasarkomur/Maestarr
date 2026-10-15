"""Save a turn's progress as it happens, so a cancelled turn keeps its last state.

Before every model request (the start of the turn and after each round of tool
calls) the agent's full message list is written to the conversation. If the turn
is then cut off — the user stops it, reloads the page or closes the tab — the
conversation shows everything done so far, any half-written answer, and a
"Cancelled" marker on the assistant's reply.
"""

from __future__ import annotations

import asyncio
import logging
from contextvars import ContextVar
from typing import Any, Optional

from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart

logger = logging.getLogger(__name__)

CANCELLED = "⏹ Cancelled"


class TurnRecorder:
    def __init__(self, store: Any, cid: str, history: list[ModelMessage]):
        self.store = store
        self.cid = cid
        self.latest: list[ModelMessage] = list(history)
        self.partial = ""  # text streamed since the last model request
        self.running: list[str] = []  # tools called since the last model request
        self._saving: Optional[asyncio.Task[None]] = None

    def snapshot(self, messages: list[ModelMessage]) -> None:
        self.latest = list(messages)
        self.partial = ""
        self.running = []
        self._saving = asyncio.ensure_future(self._save(self.latest))

    async def _save(self, messages: list[ModelMessage]) -> None:
        try:
            await self.store.save_messages(self.cid, messages)
        except Exception:  # noqa: BLE001 — progress saving must never break the turn
            logger.exception("could not save turn progress")

    async def cancelled(self) -> None:
        """Store the last state with whatever was being written and the marker."""
        if self._saving and not self._saving.done():
            await asyncio.shield(self._saving)
        await self.store.save_messages(self.cid, mark_cancelled(self.latest, self.partial, self.running))


def mark_cancelled(history: list[ModelMessage], partial: str = "", running: Optional[list[str]] = None) -> list[ModelMessage]:
    """History plus an assistant reply holding the half-written text, the steps that
    were still running, and the marker.

    >>> from pydantic_ai.messages import ModelRequest, UserPromptPart
    >>> out = mark_cancelled([ModelRequest(parts=[UserPromptPart(content="hi")])], "Let me che", ["disk_usage"])
    >>> [p.content for p in out[-1].parts]
    ['Let me che', '_Stopped while running: disk usage_', '⏹ Cancelled']
    >>> len(mark_cancelled(out)) == len(out)  # never marked twice
    True
    """
    last = history[-1] if history else None
    if isinstance(last, ModelResponse) and any(isinstance(p, TextPart) and p.content == CANCELLED for p in last.parts):
        return history
    parts: list[Any] = [TextPart(content=partial)] if partial.strip() else []
    if running:
        names = ", ".join(dict.fromkeys(r.replace("_", " ") for r in running))
        parts.append(TextPart(content=f"_Stopped while running: {names}_"))
    return [*history, ModelResponse(parts=[*parts, TextPart(content=CANCELLED)])]


TURN: ContextVar[Optional[TurnRecorder]] = ContextVar("maestarr_turn", default=None)


async def record_progress(messages: list[ModelMessage]) -> list[ModelMessage]:
    """History processor: snapshot the turn before each model request."""
    recorder = TURN.get()
    if recorder is not None:
        recorder.snapshot(messages)
    return messages
