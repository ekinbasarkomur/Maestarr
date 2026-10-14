"""Telegram channel (aiogram 3).

Only chat ids listed in TELEGRAM_ALLOWED_CHAT_IDS get an answer. Each chat is
one conversation, persisted in the store. When the agent wants to do something
that needs approval, the bot sends one message per pending action with
Approve / Deny buttons; once every pending action has an answer the run is
resumed with the decisions.

Runs inside the API process (started from the FastAPI lifespan) or alone via
`maestarr telegram`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any, Optional

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatAction
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from pydantic_ai import DeferredToolRequests, DeferredToolResults, ToolDenied

from maestarr.config import secret
from maestarr.services import Services
from maestarr.store import Store, title_from

logger = logging.getLogger(__name__)

MAX_LEN = 4000
HELP = (
    "Hi, I'm Maestarr. Ask me things like:\n"
    "• recommend me a melancholic film\n"
    "• what is downloading right now?\n"
    "• find the best release of The Wire season 2\n"
    "• how much space is left?\n\n"
    "/new starts a fresh conversation."
)


def chunks(text: str, size: int = MAX_LEN) -> list[str]:
    """Split on paragraph/line boundaries under Telegram's message limit.

    >>> [len(c) for c in chunks("a" * 5000 + "\\n" + "b" * 10, 4000)]
    [4000, 1011]
    """
    out: list[str] = []
    rest = text.strip()
    while len(rest) > size:
        cut = rest.rfind("\n", 0, size)
        if cut < size // 2:
            cut = size
        out.append(rest[:cut])
        rest = rest[cut:].lstrip("\n")
    if rest:
        out.append(rest)
    return out or ["(empty reply)"]


class TelegramChannel:
    def __init__(self, svc: Services, store: Store, bot: Bot):
        self.svc = svc
        self.store = store
        self.bot = bot
        self.allowed = set(svc.settings.TELEGRAM_ALLOWED_CHAT_IDS)
        self._locks: dict[int, asyncio.Lock] = {}

    def allowed_chat(self, chat_id: int) -> bool:
        return chat_id in self.allowed

    def lock(self, chat_id: int) -> asyncio.Lock:
        return self._locks.setdefault(chat_id, asyncio.Lock())

    async def conversation(self, chat_id: int, first_text: str = "") -> str:
        row = await self.store.by_external("telegram", str(chat_id))
        if row:
            return row["id"]
        return await self.store.create(channel="telegram", external_id=str(chat_id), title=title_from(first_text) or "Telegram")

    async def typing(self, chat_id: int) -> None:
        while True:
            with contextlib.suppress(Exception):
                await self.bot.send_chat_action(chat_id, ChatAction.TYPING)
            await asyncio.sleep(4.5)

    async def run(self, chat_id: int, cid: str, *, prompt: Optional[str] = None,
                  results: Optional[DeferredToolResults] = None) -> None:
        from maestarr.agent.agent import get_agent

        history = await self.store.messages(cid)
        typing = asyncio.create_task(self.typing(chat_id))
        try:
            result = await get_agent().run(
                prompt, message_history=history or None, deferred_tool_results=results, deps=self.svc
            )
        except Exception as exc:  # noqa: BLE001 — tell the user instead of going silent
            logger.exception("agent run failed")
            await self.bot.send_message(chat_id, f"Something went wrong: {exc}")
            return
        finally:
            typing.cancel()
        await self.store.save_messages(cid, result.all_messages())
        output = result.output
        if isinstance(output, DeferredToolRequests):
            await self.ask_approvals(chat_id, cid, output)
        else:
            for part in chunks(str(output)):
                await self.bot.send_message(chat_id, part)

    async def ask_approvals(self, chat_id: int, cid: str, requests: DeferredToolRequests) -> None:
        pending: dict[str, Any] = {"decisions": {}, "calls": []}
        for call in requests.approvals:
            meta = requests.metadata.get(call.tool_call_id) or {}
            summary = meta.get("summary") or f"{call.tool_name}({call.args_as_json_str()})"
            pending["calls"].append(call.tool_call_id)
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(text="✅ Approve", callback_data=f"ap:{call.tool_call_id}:1"[:64]),
                    InlineKeyboardButton(text="✖️ Deny", callback_data=f"ap:{call.tool_call_id}:0"[:64]),
                ]]
            )
            await self.bot.send_message(chat_id, f"Approval needed:\n{summary}", reply_markup=keyboard)
        await self.store.set_pending(cid, pending)

    async def decide(self, chat_id: int, call_id: str, approved: bool) -> Optional[str]:
        cid = await self.conversation(chat_id)
        pending = await self.store.pending(cid)
        if not pending or call_id not in pending["calls"]:
            return "This request is no longer pending."
        pending["decisions"][call_id] = approved
        await self.store.set_pending(cid, pending)
        if len(pending["decisions"]) < len(pending["calls"]):
            return "Noted — waiting for the other decisions."
        await self.store.set_pending(cid, None)
        approvals: dict[str, Any] = {
            k: (True if ok else ToolDenied("The user denied this action.")) for k, ok in pending["decisions"].items()
        }
        await self.run(chat_id, cid, results=DeferredToolResults(approvals=approvals))
        return None


def build_dispatcher(channel: TelegramChannel) -> Dispatcher:
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def start(message: Message) -> None:
        if not channel.allowed_chat(message.chat.id):
            await message.answer(
                f"Hi! This chat's id is {message.chat.id}.\n"
                "Add it under Settings → Telegram → Allowed chat ids in Maestarr, then send /start again."
            )
            return
        await message.answer(HELP)

    @dp.message(Command("new"))
    async def new(message: Message) -> None:
        if not channel.allowed_chat(message.chat.id):
            return
        await channel.store.create(channel="telegram", external_id=str(message.chat.id), title="Telegram")
        await message.answer("Started a new conversation.")

    @dp.message(Command("status"))
    async def status(message: Message) -> None:
        if not channel.allowed_chat(message.chat.id):
            return
        rows = await channel.svc.status()
        lines = [
            f"{'🟢' if s.ok else ('🔴' if s.configured else '⚪️')} {s.name}" + (f" {s.version}" if s.version else "")
            for s in rows
        ]
        await message.answer("\n".join(lines))

    @dp.message(F.text)
    async def text(message: Message) -> None:
        chat_id = message.chat.id
        if not channel.allowed_chat(chat_id):
            logger.warning("ignored message from chat %s", chat_id)
            return
        async with channel.lock(chat_id):
            cid = await channel.conversation(chat_id, message.text or "")
            if await channel.store.pending(cid):
                await channel.store.set_pending(cid, None)  # a new message abandons open approvals
            await channel.run(chat_id, cid, prompt=message.text)

    @dp.callback_query(F.data.startswith("ap:"))
    async def approval(query: CallbackQuery) -> None:
        chat_id = query.message.chat.id if query.message else query.from_user.id
        if not channel.allowed_chat(chat_id):
            await query.answer("Not allowed")
            return
        _, call_id, flag = (query.data or "").rsplit(":", 2) if (query.data or "").count(":") >= 2 else ("", "", "")
        approved = flag == "1"
        await query.answer("Approved" if approved else "Denied")
        if isinstance(query.message, Message):
            with contextlib.suppress(Exception):
                await query.message.edit_reply_markup(reply_markup=None)
                await query.message.answer("✅ Approved" if approved else "✖️ Denied")
        async with channel.lock(chat_id):
            note = await channel.decide(chat_id, call_id.removeprefix("ap:"), approved)
        if note:
            await channel.bot.send_message(chat_id, note)

    return dp


async def run_bot(svc: Services, store: Store) -> None:
    token = secret(svc.settings.TELEGRAM_BOT_TOKEN)
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    bot = Bot(token)
    channel = TelegramChannel(svc, store, bot)
    dp = build_dispatcher(channel)
    logger.info("telegram bot polling (allowed chats: %s)", sorted(channel.allowed))
    try:
        await dp.start_polling(bot, handle_signals=False)
    finally:
        await bot.session.close()
