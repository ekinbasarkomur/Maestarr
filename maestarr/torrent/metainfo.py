"""Read what is inside a torrent: `.torrent` metainfo and magnet links."""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import parse_qs, unquote, urlparse

from maestarr.domain import TorrentContents, TorrentFile
from maestarr.torrent.bencode import BencodeError, decode, info_span


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def parse_torrent(data: bytes) -> TorrentContents:
    """Parse `.torrent` bytes into a file list, v1 infohash and trackers.

    >>> from maestarr.torrent.bencode import encode
    >>> raw = encode({"announce": "udp://t:1/announce", "info": {"name": "Pack",
    ...     "piece length": 16384, "pieces": b"", "files": [
    ...     {"length": 5, "path": ["S01", "a.mkv"]}, {"length": 2, "path": ["readme.txt"]}]}})
    >>> t = parse_torrent(raw)
    >>> [f.path for f in t.files], t.total_size, len(t.info_hash), t.trackers
    (['Pack/S01/a.mkv', 'Pack/readme.txt'], 7, 40, ['udp://t:1/announce'])
    """
    try:
        meta = decode(data)
        start, end = info_span(data)
    except (BencodeError, ValueError) as exc:
        raise ValueError(f"not a valid .torrent file: {exc}") from exc
    info = meta.get(b"info") or {}
    name = _text(info.get(b"name.utf-8") or info.get(b"name") or "")
    files: list[TorrentFile] = []
    if b"files" in info:
        for entry in info[b"files"]:
            parts = entry.get(b"path.utf-8") or entry.get(b"path") or []
            path = "/".join([name, *(_text(p) for p in parts)])
            files.append(TorrentFile(path=path, size=int(entry.get(b"length", 0))))
    elif b"length" in info:
        files.append(TorrentFile(path=name, size=int(info[b"length"])))
    elif b"file tree" in info:  # BitTorrent v2-only torrent
        files.extend(_walk_v2_tree(info[b"file tree"], [name]))
    trackers: list[str] = []
    if b"announce" in meta:
        trackers.append(_text(meta[b"announce"]))
    for tier in meta.get(b"announce-list") or []:
        for url in tier if isinstance(tier, list) else [tier]:
            text = _text(url)
            if text not in trackers:
                trackers.append(text)
    return TorrentContents(
        name=name,
        info_hash=hashlib.sha1(data[start:end]).hexdigest(),
        files=files,
        trackers=trackers,
        source="torrent-file",
    )


def _walk_v2_tree(tree: dict[bytes, Any], prefix: list[str]) -> list[TorrentFile]:
    out: list[TorrentFile] = []
    for key, node in tree.items():
        if key == b"" and isinstance(node, dict):
            out.append(TorrentFile(path="/".join(prefix), size=int(node.get(b"length", 0))))
        elif isinstance(node, dict):
            out.extend(_walk_v2_tree(node, [*prefix, _text(key)]))
    return out


@dataclass
class Magnet:
    info_hash: str  # 40-char lowercase hex (v1)
    name: Optional[str] = None
    trackers: list[str] = field(default_factory=list)
    size: Optional[int] = None


def parse_magnet(uri: str) -> Magnet:
    """Parse a magnet URI; base32 infohashes are converted to hex.

    >>> m = parse_magnet("magnet:?xt=urn:btih:0B5543F0C16F2C0C957D20FF884B57BA22908AA9"
    ...                  "&dn=My%20Pack&tr=udp%3A%2F%2Ftracker.example%3A1337%2Fannounce&xl=42")
    >>> m.info_hash, m.name, m.trackers, m.size
    ('0b5543f0c16f2c0c957d20ff884b57ba22908aa9', 'My Pack', ['udp://tracker.example:1337/announce'], 42)
    >>> parse_magnet("magnet:?xt=urn:btih:BNKUH4GBN4WAZFL5ED7YQS2XXIRJBCVJ").info_hash
    '0b5543f0c16f2c0c957d20ff884b57ba22908aa9'
    """
    parsed = urlparse(uri)
    if parsed.scheme != "magnet":
        raise ValueError("not a magnet URI")
    query = parse_qs(parsed.query)
    info_hash: Optional[str] = None
    for xt in query.get("xt", []):
        if xt.lower().startswith("urn:btih:"):
            raw = xt[9:]
            if len(raw) == 40:
                info_hash = raw.lower()
            elif len(raw) == 32:
                info_hash = base64.b32decode(raw.upper()).hex()
    if not info_hash:
        raise ValueError("magnet has no BitTorrent v1 infohash")
    size = query.get("xl", [None])[0]
    return Magnet(
        info_hash=info_hash,
        name=unquote(query["dn"][0]) if "dn" in query else None,
        trackers=list(dict.fromkeys(query.get("tr", []))),
        size=int(size) if size and size.isdigit() else None,
    )


def build_magnet(info_hash: str, name: Optional[str] = None, trackers: Optional[list[str]] = None) -> str:
    """Build a magnet URI.

    >>> build_magnet("AB" * 20, "x y", ["udp://t:1/a"])
    'magnet:?xt=urn:btih:abababababababababababababababababababab&dn=x%20y&tr=udp%3A%2F%2Ft%3A1%2Fa'
    """
    from urllib.parse import quote

    parts = [f"xt=urn:btih:{info_hash.lower()}"]
    if name:
        parts.append(f"dn={quote(name)}")
    parts.extend(f"tr={quote(t, safe='')}" for t in trackers or [])
    return "magnet:?" + "&".join(parts)


# Public trackers that still answer scrapes; used as a fallback when a magnet
# carries none of its own.
FALLBACK_TRACKERS = [
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.stealth.si:80/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://exodus.desync.com:6969/announce",
    "udp://explodie.org:6969/announce",
    "udp://open.demonii.com:1337/announce",
]
