"""Which channel the current agent run answers on (web, telegram, mcp).

Set by the channel before it runs the agent; the dynamic instructions read it
to adapt the reply's formatting (Telegram cannot show tables).
"""

from __future__ import annotations

from contextvars import ContextVar

CHANNEL: ContextVar[str] = ContextVar("maestarr_channel", default="web")
