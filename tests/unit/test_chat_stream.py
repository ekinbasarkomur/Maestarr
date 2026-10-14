"""The chat endpoint end to end: Vercel AI SDK v6 stream, approvals, history."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx
import pytest
from pydantic_ai.messages import ModelMessage, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

import maestarr.agent.agent as agent_module
from maestarr.agent.agent import create_agent
from maestarr.app import app
from maestarr.config import get_settings


def _tool_done(messages: list[ModelMessage]) -> bool:
    return any(isinstance(p, ToolReturnPart) for m in messages for p in getattr(m, "parts", []))


async def stream(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[Any]:
    if _tool_done(messages):
        yield "Deleted it."
    else:
        yield {0: DeltaToolCall(name="delete_movie_file", json_args='{"movie_id": 7}', tool_call_id="call-1")}


@pytest.fixture
async def client(monkeypatch):
    agent = create_agent(get_settings(), model=FunctionModel(stream_function=stream))
    monkeypatch.setattr(agent_module, "get_agent", lambda: agent)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/auth/setup-account", json={"username": "owner", "password": "longpassword"})
        assert r.status_code == 200
        yield c


def _events(body: str) -> list[dict[str, Any]]:
    out = []
    for line in body.splitlines():
        if line.startswith("data: ") and line != "data: [DONE]":
            out.append(json.loads(line[6:]))
    return out


async def test_approval_round_trip(client):
    user = {"id": "u1", "role": "user", "parts": [{"type": "text", "text": "delete movie 7"}]}
    r = await client.post("/api/chat", json={"trigger": "submit-message", "id": "chat-1", "messages": [user]})
    assert r.status_code == 200, r.text
    events = _events(r.text)
    types = [e["type"] for e in events]
    assert "tool-input-available" in types
    summary = next(e for e in events if e["type"] == "data-approval")
    assert summary["data"]["summary"] == "DELETE the file of radarr item 7"
    approval = next(e for e in events if e["type"] == "tool-approval-request")
    assert approval["toolCallId"] == "call-1"
    assert types.index("data-approval") < types.index("tool-approval-request")

    # The browser answers with the assistant message carrying the approval.
    assistant = {
        "id": "a1",
        "role": "assistant",
        "parts": [
            {
                "type": "tool-delete_movie_file",
                "toolCallId": "call-1",
                "state": "approval-responded",
                "input": {"movie_id": 7},
                "approval": {"id": "call-1", "approved": True},
            }
        ],
    }
    r = await client.post(
        "/api/chat", json={"trigger": "submit-message", "id": "chat-1", "messages": [user, assistant]}
    )
    events = _events(r.text)
    output = next(e for e in events if e["type"] == "tool-output-available")
    # Radarr is not configured in tests: the tool ran and reported that.
    assert "not configured" in json.dumps(output["output"])
    assert any(e["type"] == "text-delta" and "Deleted" in e["delta"] for e in events)

    # The conversation was stored and can be reopened.
    conv = (await client.get("/api/conversations/chat-1")).json()
    assert conv["title"] == "delete movie 7"
    assert len(conv["messages"]) >= 2
    assert [c["id"] for c in (await client.get("/api/conversations")).json()] == ["chat-1"]


async def test_denied_tool_is_not_run(client):
    user = {"id": "u1", "role": "user", "parts": [{"type": "text", "text": "delete movie 7"}]}
    await client.post("/api/chat", json={"trigger": "submit-message", "id": "chat-2", "messages": [user]})
    assistant = {
        "id": "a1",
        "role": "assistant",
        "parts": [
            {
                "type": "tool-delete_movie_file",
                "toolCallId": "call-1",
                "state": "approval-responded",
                "input": {"movie_id": 7},
                "approval": {"id": "call-1", "approved": False, "reason": "not now"},
            }
        ],
    }
    r = await client.post("/api/chat", json={"trigger": "submit-message", "id": "chat-2", "messages": [user, assistant]})
    types = [e["type"] for e in _events(r.text)]
    assert "tool-output-denied" in types
    assert "tool-output-available" not in types
