"""Markdown from the agent → Telegram's HTML subset.

Telegram renders only <b>, <i>, <u>, <s>, <code>, <pre>, <a> and <blockquote>;
raw Markdown shows up as literal ``**`` and ``|---|``. Tables, which Telegram
cannot show at all, become one bullet per row.
"""

from __future__ import annotations

import html
import re

_FENCE = re.compile(r"```[^\n`]*\n(.*?)```", re.S)
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)")
_BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*|__(?=\S)(.+?)(?<=\S)__")
_ITALIC = re.compile(r"(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])|(?<![\w_])_(?=\S)([^_\n]+?)(?<=\S)_(?![\w_])")
_STRIKE = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~")
_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")
_BULLET = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_RULE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _table(rows: list[str]) -> list[str]:
    """A Markdown table as bullets: first cell bold, the rest labelled by header.

    >>> _table(["| Release | Size | Seeders |", "|---|---|---|", "| FGT | 29 GB | 54 |", "| BHD | 7.6 GB | 26 |"])
    ['• **FGT** — Size: 29 GB · Seeders: 54', '• **BHD** — Size: 7.6 GB · Seeders: 26']
    """
    header = _cells(rows[0])
    body = [r for r in rows[1:] if not _TABLE_SEP.match(r)]
    out = []
    for row in body:
        cells = _cells(row)
        rest = [
            f"{header[i]}: {c}" if i < len(header) and header[i] else c
            for i, c in enumerate(cells[1:], start=1)
            if c
        ]
        out.append(f"• **{cells[0]}**" + (" — " + " · ".join(rest) if rest else ""))
    return out


def _inline(text: str) -> str:
    """Escape, then apply inline formatting (code spans are kept literal)."""
    codes: list[str] = []

    def keep(match: re.Match[str]) -> str:
        codes.append(f"<code>{html.escape(match.group(1))}</code>")
        return f"\x00{len(codes) - 1}\x00"

    text = _INLINE_CODE.sub(keep, text)
    links: list[str] = []

    def link(match: re.Match[str]) -> str:
        links.append(f'<a href="{html.escape(match.group(2), quote=True)}">{html.escape(match.group(1))}</a>')
        return f"\x01{len(links) - 1}\x01"

    text = _LINK.sub(link, text)
    text = html.escape(text, quote=False)
    text = _BOLD.sub(lambda m: f"<b>{m.group(1) or m.group(2)}</b>", text)
    text = _STRIKE.sub(lambda m: f"<s>{m.group(1)}</s>", text)
    text = _ITALIC.sub(lambda m: f"<i>{m.group(1) or m.group(2)}</i>", text)
    text = re.sub(r"\x01(\d+)\x01", lambda m: links[int(m.group(1))], text)
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], text)


def to_telegram_html(markdown: str) -> str:
    """
    >>> to_telegram_html("## Picks\\n\\n**Se7en** (1995) — *dark* & rainy\\n- one\\n  - two\\n\\n`a<b>`")
    '<b>Picks</b>\\n\\n<b>Se7en</b> (1995) — <i>dark</i> &amp; rainy\\n• one\\n    ◦ two\\n\\n<code>a&lt;b&gt;</code>'
    >>> to_telegram_html("```\\nx < y\\n```\\nsnake_case_name stays")
    '<pre>x &lt; y</pre>\\nsnake_case_name stays'
    >>> to_telegram_html("> quoted\\n> more")
    '<blockquote>quoted\\nmore</blockquote>'
    """
    blocks: list[str] = []

    def fence(match: re.Match[str]) -> str:
        blocks.append(f"<pre>{html.escape(match.group(1).rstrip())}</pre>")
        return f"\x02{len(blocks) - 1}\x02"

    text = _FENCE.sub(fence, markdown.replace("\r\n", "\n"))
    lines = text.split("\n")
    out: list[str] = []
    quote: list[str] = []
    i = 0

    def flush_quote() -> None:
        if quote:
            out.append("<blockquote>" + "\n".join(quote) + "</blockquote>")
            quote.clear()

    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith("|") and i + 1 < len(lines) and _TABLE_SEP.match(lines[i + 1]):
            flush_quote()
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append(lines[i])
                i += 1
            out.extend(_inline(r) for r in _table(rows))
            continue
        if line.startswith(">"):
            quote.append(_inline(line[1:].lstrip()))
            i += 1
            continue
        flush_quote()
        heading = _HEADING.match(line)
        bullet = _BULLET.match(line)
        if heading:
            out.append(f"<b>{_inline(heading.group(1))}</b>")
        elif _RULE.match(line):
            out.append("—")
        elif bullet:
            depth = len(bullet.group(1).replace("\t", "  ")) // 2
            out.append("    " * depth + ("◦ " if depth else "• ") + _inline(bullet.group(2)))
        else:
            out.append(_inline(line))
        i += 1
    flush_quote()
    result = "\n".join(out)
    result = re.sub(r"\x02(\d+)\x02", lambda m: blocks[int(m.group(1))], result)
    return re.sub(r"\n{3,}", "\n\n", result).strip()


def to_plain(markdown: str) -> str:
    """The same text without any markup, for when Telegram rejects the HTML."""
    return re.sub(r"<[^>]+>", "", to_telegram_html(markdown)).replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
