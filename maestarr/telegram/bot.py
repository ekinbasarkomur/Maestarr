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
import html
import logging
import uuid
from typing import Any, Optional

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from pydantic_ai import DeferredToolRequests, DeferredToolResults, ToolDenied

from maestarr.agent.channel import CHANNEL
from maestarr.config import secret
from maestarr.services import Services
from maestarr.store import Store, title_from
from maestarr.telegram.format import to_plain, to_telegram_html

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
        self._picks: dict[str, dict[str, Any]] = {}  # pick-list buttons → the releases they stand for

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
        token = CHANNEL.set("telegram")
        try:
            result = await get_agent().run(
                prompt, message_history=history or None, deferred_tool_results=results, deps=self.svc
            )
        except Exception as exc:  # noqa: BLE001 — tell the user instead of going silent
            logger.exception("agent run failed")
            await self.bot.send_message(chat_id, f"Something went wrong: {exc}")
            return
        finally:
            CHANNEL.reset(token)
            typing.cancel()
        await self.store.save_messages(cid, result.all_messages())
        await self.send_extras(chat_id, result.new_messages())
        output = result.output
        if isinstance(output, DeferredToolRequests):
            await self.ask_approvals(chat_id, cid, output)
        else:
            await self.send_text(chat_id, str(output))

    async def send_text(self, chat_id: int, text: str, **kwargs: Any) -> None:
        """Markdown → Telegram HTML; plain text if Telegram rejects the markup."""
        for part in chunks(text, 3500):
            try:
                await self.bot.send_message(chat_id, to_telegram_html(part), parse_mode="HTML",
                                            disable_web_page_preview=True, **kwargs)
            except TelegramBadRequest as exc:
                logger.warning("telegram rejected HTML (%s); sending plain text", exc)
                await self.bot.send_message(chat_id, to_plain(part), **kwargs)

    async def send_extras(self, chat_id: int, messages: list[Any]) -> None:
        """What the web chat shows as cards and pick lists, in Telegram's own form."""
        for message in messages:
            for part in getattr(message, "parts", []):
                if getattr(part, "part_kind", "") != "tool-return" or not isinstance(part.content, dict):
                    continue
                try:
                    if part.tool_name == "show_recommendations" and part.content.get("cards"):
                        await self.send_cards(chat_id, part.content["cards"])
                    elif part.tool_name in ("judge_releases", "more_releases") and part.content.get("assessed"):
                        await self.send_picker(chat_id, part.content)
                except Exception:  # noqa: BLE001 — extras must never lose the reply
                    logger.exception("could not send %s to telegram", part.tool_name)

    async def send_cards(self, chat_id: int, cards: list[dict[str, Any]]) -> None:
        """Recommendations as a poster album; each caption carries the reason."""
        from aiogram.types import InputMediaPhoto

        def caption(c: dict[str, Any]) -> str:
            head = f"<b>{html.escape(str(c.get('title')))}</b>" + (f" ({c['year']})" if c.get("year") else "")
            rating = f" · ⭐ {c['rating']}" if c.get("rating") else ""
            return f"{head}{rating}\n{html.escape(str(c.get('why') or ''))}"[:1000]

        with_image = [c for c in cards if c.get("image")][:10]
        if len(with_image) >= 2:
            media = [InputMediaPhoto(media=c["image"], caption=caption(c), parse_mode="HTML") for c in with_image]
            try:
                await self.bot.send_media_group(chat_id, media=media)  # type: ignore[arg-type]
                return
            except TelegramBadRequest as exc:
                logger.warning("poster album failed (%s); sending a list", exc)
        elif len(with_image) == 1:
            with contextlib.suppress(TelegramBadRequest):
                await self.bot.send_photo(chat_id, with_image[0]["image"], caption=caption(with_image[0]), parse_mode="HTML")
                return
        await self.bot.send_message(chat_id, "\n\n".join(caption(c) for c in cards), parse_mode="HTML")

    async def send_picker(self, chat_id: int, data: dict[str, Any]) -> None:
        """Judged releases as a numbered list with a download button per release."""
        rows = data["assessed"][:5]
        chosen = (data.get("verdict") or {}).get("chosen_guid")
        key = uuid.uuid4().hex[:10]
        self._picks[key] = {"subject": data.get("subject"), "rows": rows, "results_id": data.get("results_id"),
                            "next_offset": data.get("next_offset", 0)}
        lines = [f"<b>{html.escape(str(data.get('subject')))}</b>"]
        for i, r in enumerate(rows, start=1):
            seeders = r.get("live_seeders") if r.get("live_seeders") is not None else r.get("indexer_seeders")
            star = " ⭐" if r["guid"] == chosen else ""
            lines.append(
                f"\n<b>{i}.</b> {html.escape(r['title'][:90])}{star}\n"
                f"    {r['size_gb']} GB · {seeders if seeders is not None else '?'} seeders · score {round(r['score'])}"
                + (f"\n    <i>{html.escape(r['blockers'][0][:90])}</i>" if r.get("blockers") else "")
            )
        buttons = [InlineKeyboardButton(text=f"⬇️ {i}", callback_data=f"pk:{key}:{i - 1}") for i in range(1, len(rows) + 1)]
        keyboard = [buttons]
        if data.get("results_id") and data.get("more_available"):
            keyboard.append([InlineKeyboardButton(text=f"➕ More results ({data['more_available']})", callback_data=f"pk:{key}:more")])
        await self.bot.send_message(chat_id, "\n".join(lines), parse_mode="HTML",
                                    reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

    def pick_prompt(self, key: str, choice: str) -> Optional[str]:
        entry = self._picks.get(key)
        if not entry:
            return None
        if choice == "more":
            return (f"Show more results for {entry['subject']} "
                    f"(results {entry['results_id']}, offset {entry['next_offset']}).")
        row = entry["rows"][int(choice)]
        return f'Download "{row["title"]}" (guid {row["guid"]}) for {entry["subject"]}.'

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
                "To connect it, press Connect under Settings → Telegram in Maestarr and send /start again "
                "(or add the id to Allowed chat ids yourself)."
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

    @dp.callback_query(F.data.startswith("pk:"))
    async def pick(query: CallbackQuery) -> None:
        chat_id = query.message.chat.id if query.message else query.from_user.id
        if not channel.allowed_chat(chat_id):
            await query.answer("Not allowed")
            return
        _, key, choice = (query.data or "::").split(":", 2)
        prompt = channel.pick_prompt(key, choice)
        if not prompt:
            await query.answer("Those results expired — ask again")
            return
        await query.answer("On it")
        async with channel.lock(chat_id):
            cid = await channel.conversation(chat_id)
            await channel.bot.send_message(chat_id, f"➡️ {prompt}")
            await channel.run(chat_id, cid, prompt=prompt)

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


def make_bot(token: str) -> Bot:
    """A Bot that talks to Telegram through Settings → Proxy when one is set."""
    from maestarr import net

    proxy = net.proxy_for("https://api.telegram.org")
    if not proxy:
        return Bot(token)
    from aiogram.client.session.aiohttp import AiohttpSession

    try:
        return Bot(token, session=AiohttpSession(proxy=proxy))
    except Exception as exc:  # noqa: BLE001 — SOCKS needs aiohttp-socks; fall back to direct
        logger.warning("telegram proxy unavailable (%s); connecting directly", exc)
        return Bot(token)


async def run_bot(svc: Services, store: Store) -> None:
    token = secret(svc.settings.TELEGRAM_BOT_TOKEN)
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    bot = make_bot(token)
    channel = TelegramChannel(svc, store, bot)
    dp = build_dispatcher(channel)
    logger.info("telegram bot polling (allowed chats: %s)", sorted(channel.allowed))
    try:
        await dp.start_polling(bot, handle_signals=False)
    finally:
        await bot.session.close()
