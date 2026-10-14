"""SQLite persistence: conversations and their pydantic-ai message history.

One table is enough: a conversation row holds its full model history (as
pydantic-ai's own JSON) and, for chat channels without a stateful client
(Telegram), the approvals it is waiting on.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import aiosqlite
from pydantic_ai import ModelMessagesTypeAdapter
from pydantic_ai.messages import ModelMessage

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    channel TEXT NOT NULL DEFAULT 'web',
    external_id TEXT,
    title TEXT NOT NULL DEFAULT 'New chat',
    messages BLOB,
    pending TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS conversations_external ON conversations(channel, external_id);
"""


class Store:
    def __init__(self, path: Path):
        self.path = path
        self._ready = False

    async def _db(self) -> aiosqlite.Connection:
        db = await aiosqlite.connect(self.path)
        db.row_factory = aiosqlite.Row
        if not self._ready:
            await db.executescript(SCHEMA)
            await db.commit()
            self._ready = True
        return db

    async def create(self, *, channel: str = "web", external_id: Optional[str] = None,
                     conversation_id: Optional[str] = None, title: str = "New chat") -> str:
        cid = conversation_id or uuid.uuid4().hex
        now = time.time()
        db = await self._db()
        try:
            await db.execute(
                "INSERT OR IGNORE INTO conversations (id, channel, external_id, title, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                (cid, channel, external_id, title, now, now),
            )
            await db.commit()
        finally:
            await db.close()
        return cid

    async def get(self, cid: str) -> Optional[dict[str, Any]]:
        db = await self._db()
        try:
            async with db.execute("SELECT * FROM conversations WHERE id = ?", (cid,)) as cur:
                row = await cur.fetchone()
        finally:
            await db.close()
        return dict(row) if row else None

    async def by_external(self, channel: str, external_id: str) -> Optional[dict[str, Any]]:
        db = await self._db()
        try:
            async with db.execute(
                "SELECT * FROM conversations WHERE channel = ? AND external_id = ? ORDER BY updated_at DESC LIMIT 1",
                (channel, external_id),
            ) as cur:
                row = await cur.fetchone()
        finally:
            await db.close()
        return dict(row) if row else None

    async def list(self, channel: Optional[str] = "web", limit: int = 50) -> list[dict[str, Any]]:
        db = await self._db()
        try:
            query = "SELECT id, channel, title, created_at, updated_at FROM conversations"
            args: tuple[Any, ...] = ()
            if channel:
                query += " WHERE channel = ?"
                args = (channel,)
            query += " ORDER BY updated_at DESC LIMIT ?"
            async with db.execute(query, (*args, limit)) as cur:
                rows = await cur.fetchall()
        finally:
            await db.close()
        return [dict(r) for r in rows]

    async def messages(self, cid: str) -> list[ModelMessage]:
        row = await self.get(cid)
        if not row or not row.get("messages"):
            return []
        return list(ModelMessagesTypeAdapter.validate_json(row["messages"]))

    async def save_messages(self, cid: str, messages: list[ModelMessage], *, title: Optional[str] = None) -> None:
        blob = ModelMessagesTypeAdapter.dump_json(messages)
        db = await self._db()
        try:
            if title:
                await db.execute(
                    "UPDATE conversations SET messages = ?, title = ?, updated_at = ? WHERE id = ?",
                    (blob, title[:80], time.time(), cid),
                )
            else:
                await db.execute(
                    "UPDATE conversations SET messages = ?, updated_at = ? WHERE id = ?", (blob, time.time(), cid)
                )
            await db.commit()
        finally:
            await db.close()

    async def set_pending(self, cid: str, pending: Optional[dict[str, Any]]) -> None:
        db = await self._db()
        try:
            await db.execute(
                "UPDATE conversations SET pending = ?, updated_at = ? WHERE id = ?",
                (json.dumps(pending) if pending else None, time.time(), cid),
            )
            await db.commit()
        finally:
            await db.close()

    async def pending(self, cid: str) -> Optional[dict[str, Any]]:
        row = await self.get(cid)
        return json.loads(row["pending"]) if row and row.get("pending") else None

    async def rename(self, cid: str, title: str) -> None:
        db = await self._db()
        try:
            await db.execute("UPDATE conversations SET title = ? WHERE id = ?", (title[:80], cid))
            await db.commit()
        finally:
            await db.close()

    async def delete(self, cid: str) -> None:
        db = await self._db()
        try:
            await db.execute("DELETE FROM conversations WHERE id = ?", (cid,))
            await db.commit()
        finally:
            await db.close()


def title_from(text: str) -> str:
    """
    >>> title_from("  recommend me something   melancholic\\nplease ")
    'recommend me something melancholic please'
    """
    return " ".join(text.split())[:60] or "New chat"
