"""Vercel AI stream with readable approval cards.

pydantic-ai streams a tool-approval request with ids only. Maestarr's write
tools attach a one-line summary ("Download X (8.1 GB) via radarr") to each
request; this subclass emits it as a `data-approval` part right before the
approval request, so the UI can show what is being approved, not just which
function.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

from pydantic import BaseModel
from pydantic_ai import DeferredToolRequests
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from pydantic_ai.ui.vercel_ai._event_stream import VercelAIEventStream
from pydantic_ai.ui.vercel_ai.request_types import ReasoningUIPart, StepStartUIPart, TextUIPart
from pydantic_ai.ui.vercel_ai.response_types import BaseChunk, DataChunk


def _fields(model: type[BaseModel]) -> frozenset[str]:
    return frozenset((f.alias or name) for name, f in model.model_fields.items())


# The AI SDK client keeps extra keys on some parts it assembled from the stream
# (an `id` on reasoning parts, for one); pydantic-ai's request models forbid
# extras, so one "thinking" reply made every later message in that chat fail
# with a 422. Keep only the keys each simple part type defines.
_PART_FIELDS = {
    "text": _fields(TextUIPart),
    "reasoning": _fields(ReasoningUIPart),
    "step-start": _fields(StepStartUIPart),
}


def clean_body(body: bytes) -> bytes:
    """Drop unknown keys from text/reasoning/step-start parts of a chat request.

    >>> raw = b'{"messages": [{"parts": [{"type": "reasoning", "id": "x", "text": "", "state": "done"}]}]}'
    >>> json.loads(clean_body(raw))["messages"][0]["parts"][0]
    {'type': 'reasoning', 'text': '', 'state': 'done'}
    """
    try:
        data = json.loads(body or b"{}")
    except json.JSONDecodeError:
        return body
    for message in data.get("messages") or []:
        parts = message.get("parts") if isinstance(message, dict) else None
        if not isinstance(parts, list):
            continue
        for i, part in enumerate(parts):
            allowed = _PART_FIELDS.get(str(part.get("type"))) if isinstance(part, dict) else None
            if allowed:
                parts[i] = {k: v for k, v in part.items() if k in allowed}
    return json.dumps(data).encode()


class MaestarrEventStream(VercelAIEventStream):  # type: ignore[type-arg]
    async def handle_run_result(self, event: Any) -> AsyncIterator[BaseChunk]:
        output = event.result.output
        if self.sdk_version >= 6 and isinstance(output, DeferredToolRequests):
            for call in output.approvals:
                meta = output.metadata.get(call.tool_call_id) or {}
                yield DataChunk(
                    type="data-approval",
                    id=f"approval-{call.tool_call_id}",
                    data={"toolCallId": call.tool_call_id, "tool": call.tool_name, "summary": meta.get("summary")},
                )
        async for chunk in super().handle_run_result(event):
            yield chunk


class MaestarrAdapter(VercelAIAdapter):  # type: ignore[type-arg]
    @classmethod
    def build_run_input(cls, body: bytes) -> Any:
        return super().build_run_input(clean_body(body))

    def build_event_stream(self) -> Any:
        return MaestarrEventStream(
            self.run_input,
            accept=self.accept,
            sdk_version=self.sdk_version,
            server_message_id=self.server_message_id,
        )
