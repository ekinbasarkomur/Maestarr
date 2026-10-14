from __future__ import annotations

from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from maestarr.store import Store


async def test_conversation_roundtrip(tmp_path):
    store = Store(tmp_path / "db.sqlite3")
    cid = await store.create(title="first")
    messages = [ModelRequest(parts=[UserPromptPart(content="hi")]), ModelResponse(parts=[TextPart(content="hello")])]
    await store.save_messages(cid, messages)
    loaded = await store.messages(cid)
    assert [type(m).__name__ for m in loaded] == ["ModelRequest", "ModelResponse"]
    assert loaded[1].parts[0].content == "hello"
    assert [c["title"] for c in await store.list(channel=None)] == ["first"]
    await store.set_pending(cid, {"calls": ["a"], "decisions": {}})
    assert (await store.pending(cid))["calls"] == ["a"]
    await store.delete(cid)
    assert await store.get(cid) is None


async def test_telegram_conversation_lookup(tmp_path):
    store = Store(tmp_path / "db.sqlite3")
    cid = await store.create(channel="telegram", external_id="42")
    assert (await store.by_external("telegram", "42"))["id"] == cid
    assert await store.by_external("telegram", "43") is None
