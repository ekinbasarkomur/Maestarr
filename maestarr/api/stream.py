"""Vercel AI stream with readable approval cards.

pydantic-ai streams a tool-approval request with ids only. Maestarr's write
tools attach a one-line summary ("Download X (8.1 GB) via radarr") to each
request; this subclass emits it as a `data-approval` part right before the
approval request, so the UI can show what is being approved, not just which
function.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from pydantic_ai import DeferredToolRequests
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from pydantic_ai.ui.vercel_ai._event_stream import VercelAIEventStream
from pydantic_ai.ui.vercel_ai.response_types import BaseChunk, DataChunk


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
    def build_event_stream(self) -> Any:
        return MaestarrEventStream(
            self.run_input,
            accept=self.accept,
            sdk_version=self.sdk_version,
            server_message_id=self.server_message_id,
        )
