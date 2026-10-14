"""Live swarm numbers straight from trackers (BEP 15 UDP and BEP 48 HTTP scrape).

Indexer seeder counts are snapshots that can be weeks old; a scrape asks the
trackers right now. Trackers each see only their own share of the swarm, so the
aggregate takes the MAXIMUM across trackers, never the sum (the same peers
announce to several trackers at once).
"""

from __future__ import annotations

import asyncio
import logging
import random
import struct
from dataclasses import dataclass
from typing import Optional, Sequence
from urllib.parse import quote_from_bytes, urlparse

import httpx

from maestarr.domain import SwarmStats
from maestarr.torrent.bencode import decode

logger = logging.getLogger(__name__)

_PROTOCOL_ID = 0x41727101980
_ACTION_CONNECT = 0
_ACTION_SCRAPE = 2
_ACTION_ERROR = 3


@dataclass
class TrackerStats:
    tracker: str
    seeders: int
    leechers: int
    completed: int


class _UdpExchange(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.queue: asyncio.Queue[bytes] = asyncio.Queue()

    def datagram_received(self, data: bytes, addr: object) -> None:
        self.queue.put_nowait(data)

    def error_received(self, exc: Exception) -> None:
        logger.debug("udp tracker error: %s", exc)


async def _udp_roundtrip(
    protocol: _UdpExchange, transport: asyncio.DatagramTransport, payload: bytes, tid: int, timeout: float
) -> bytes:
    for attempt in range(2):
        transport.sendto(payload)
        try:
            while True:
                data = await asyncio.wait_for(protocol.queue.get(), timeout * (attempt + 1))
                if len(data) >= 8 and struct.unpack(">I", data[4:8])[0] == tid:
                    return data
        except asyncio.TimeoutError:
            continue
    raise TimeoutError("no answer")


async def scrape_udp(tracker: str, info_hashes: Sequence[str], timeout: float = 4.0) -> dict[str, TrackerStats]:
    """Scrape up to 74 infohashes from one UDP tracker."""
    url = urlparse(tracker)
    if not url.hostname or not url.port:
        raise ValueError(f"bad udp tracker url: {tracker}")
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        _UdpExchange, remote_addr=(url.hostname, url.port)
    )
    try:
        tid = random.getrandbits(32)
        reply = await _udp_roundtrip(
            protocol, transport, struct.pack(">QII", _PROTOCOL_ID, _ACTION_CONNECT, tid), tid, timeout
        )
        action = struct.unpack(">I", reply[:4])[0]
        if action != _ACTION_CONNECT or len(reply) < 16:
            raise ValueError("bad connect reply")
        connection_id = struct.unpack(">Q", reply[8:16])[0]
        hashes = list(info_hashes)[:74]
        tid = random.getrandbits(32)
        payload = struct.pack(">QII", connection_id, _ACTION_SCRAPE, tid) + b"".join(
            bytes.fromhex(h) for h in hashes
        )
        reply = await _udp_roundtrip(protocol, transport, payload, tid, timeout)
        action = struct.unpack(">I", reply[:4])[0]
        if action == _ACTION_ERROR:
            raise ValueError(reply[8:].decode(errors="replace"))
        if action != _ACTION_SCRAPE:
            raise ValueError("bad scrape reply")
        out: dict[str, TrackerStats] = {}
        body = reply[8:]
        for index, info_hash in enumerate(hashes):
            chunk = body[index * 12 : index * 12 + 12]
            if len(chunk) < 12:
                break
            seeders, completed, leechers = struct.unpack(">III", chunk)
            out[info_hash.lower()] = TrackerStats(tracker, seeders, leechers, completed)
        return out
    finally:
        transport.close()


def http_scrape_url(announce: str) -> Optional[str]:
    """Derive the scrape URL from an announce URL (convention, not a guarantee).

    >>> http_scrape_url("https://t.example/abc/announce?passkey=1")
    'https://t.example/abc/scrape?passkey=1'
    >>> http_scrape_url("https://t.example/announce.php") is None
    True
    """
    parsed = urlparse(announce)
    path = parsed.path
    head, _, last = path.rpartition("/")
    if not last.startswith("announce"):
        return None
    new_last = "scrape" + last[len("announce") :]
    if new_last != "scrape" and not new_last.startswith("scrape."):
        return None
    if new_last.startswith("scrape.") and new_last != "scrape":
        return None
    return parsed._replace(path=f"{head}/{new_last}").geturl()


async def scrape_http(
    tracker: str, info_hashes: Sequence[str], client: httpx.AsyncClient, timeout: float = 6.0
) -> dict[str, TrackerStats]:
    url = http_scrape_url(tracker)
    if url is None:
        raise ValueError("tracker does not support scrape")
    query = "&".join(f"info_hash={quote_from_bytes(bytes.fromhex(h))}" for h in info_hashes)
    sep = "&" if "?" in url else "?"
    response = await client.get(f"{url}{sep}{query}", timeout=timeout)
    response.raise_for_status()
    data = decode(response.content)
    files = data.get(b"files") or {}
    out: dict[str, TrackerStats] = {}
    for raw_hash, stats in files.items():
        out[raw_hash.hex()] = TrackerStats(
            tracker,
            int(stats.get(b"complete", 0)),
            int(stats.get(b"incomplete", 0)),
            int(stats.get(b"downloaded", 0)),
        )
    return out


async def scrape_many(
    info_hashes: Sequence[str],
    trackers_by_hash: dict[str, list[str]],
    *,
    max_trackers: int = 8,
    timeout: float = 4.0,
) -> dict[str, SwarmStats]:
    """Scrape every hash from its trackers concurrently and aggregate (max)."""
    hashes = [h.lower() for h in info_hashes]
    # Group hashes per tracker so each tracker gets one request.
    per_tracker: dict[str, list[str]] = {}
    for info_hash in hashes:
        for tracker in trackers_by_hash.get(info_hash, [])[:max_trackers]:
            if tracker.startswith(("udp://", "http://", "https://")):
                per_tracker.setdefault(tracker, []).append(info_hash)

    from maestarr import net

    if not net.udp_allowed():
        # A proxy cannot carry UDP; scraping directly would leak this host's IP.
        per_tracker = {t: w for t, w in per_tracker.items() if not t.startswith("udp://")}
    results: dict[str, SwarmStats] = {h: SwarmStats(method="scrape") for h in hashes}
    proxy = net.proxy_for("https://tracker.invalid")  # public trackers: proxied when a proxy is set
    async with (
        httpx.AsyncClient(follow_redirects=True, proxy=proxy) as proxied,
        httpx.AsyncClient(follow_redirects=True) as direct,
    ):

        async def one(tracker: str, wanted: list[str]) -> None:
            for h in wanted:
                results[h].trackers_tried += 1
            try:
                if tracker.startswith("udp://"):
                    stats = await scrape_udp(tracker, wanted, timeout=timeout)
                else:
                    client = proxied if net.proxy_for(tracker) else direct
                    stats = await scrape_http(tracker, wanted, client, timeout=timeout + 2)
            except Exception as exc:  # noqa: BLE001 — one bad tracker is normal
                logger.debug("scrape %s failed: %s", tracker, exc)
                return
            for h, s in stats.items():
                if h not in results:
                    continue
                agg = results[h]
                agg.trackers_answered += 1
                agg.seeders = max(agg.seeders, s.seeders)
                agg.leechers = max(agg.leechers, s.leechers)
                agg.completed = max(agg.completed or 0, s.completed)

        await asyncio.gather(*(one(t, w) for t, w in per_tracker.items()))
    for stats in results.values():
        if stats.trackers_answered == 0:
            stats.method = "none"
            stats.note = "no tracker answered the scrape"
    return results
