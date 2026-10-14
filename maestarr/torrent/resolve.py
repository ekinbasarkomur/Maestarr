"""Find out what a release really is: its file list and its live swarm.

Order of preference for the file list, cheapest and least intrusive first:

1. the release's own `.torrent` (Sonarr/Radarr/Prowlarr `downloadUrl`; Prowlarr
   answers either with the file or a redirect to a magnet),
2. a torrent already present in qBittorrent (read, never touched),
3. qBittorrent >= 5.2 `fetchMetadata` (nothing is added to the client),
4. an older qBittorrent: a tagged probe that stops on metadata and is deleted.

Live numbers come from a direct tracker scrape; when no tracker answers, the
indexer's figure is kept but marked as such.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from maestarr.clients.base import ServiceError
from maestarr.clients.qbittorrent import QBittorrentClient
from maestarr.domain import ReleaseCandidate, SwarmStats, TorrentContents, TorrentFile
from maestarr.torrent.metainfo import FALLBACK_TRACKERS, Magnet, build_magnet, parse_magnet, parse_torrent
from maestarr.torrent.scrape import scrape_many

logger = logging.getLogger(__name__)

PROBE_TAG = "maestarr-probe"


@dataclass
class Resolved:
    magnet: Optional[Magnet] = None
    contents: Optional[TorrentContents] = None
    error: Optional[str] = None

    @property
    def info_hash(self) -> Optional[str]:
        if self.contents and self.contents.info_hash:
            return self.contents.info_hash
        return self.magnet.info_hash if self.magnet else None

    @property
    def trackers(self) -> list[str]:
        trackers = list(self.contents.trackers) if self.contents else []
        if self.magnet:
            trackers += [t for t in self.magnet.trackers if t not in trackers]
        return trackers


class ReleaseResolver:
    def __init__(
        self,
        qbittorrent: Optional[QBittorrentClient],
        *,
        probe_category: str = "maestarr-probe",
        probe_timeout: float = 60.0,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.qbit = qbittorrent
        self.probe_category = probe_category
        self.probe_timeout = probe_timeout
        self._transport = transport
        self._fetch_metadata_supported: Optional[bool] = None
        self._semaphore = asyncio.Semaphore(3)

    async def download_payload(self, release: ReleaseCandidate) -> Resolved:
        """Step 1: what the indexer hands out — a .torrent or a magnet."""
        if release.magnet_url and release.magnet_url.startswith("magnet:"):
            try:
                return Resolved(magnet=parse_magnet(release.magnet_url))
            except ValueError as exc:
                return Resolved(error=str(exc))
        url = release.download_url or release.magnet_url
        if not url:
            if release.info_hash:
                return Resolved(magnet=Magnet(info_hash=release.info_hash.lower(), name=release.title))
            return Resolved(error="release has no download link")
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=False, transport=self._transport) as client:
                for _ in range(5):
                    response = await client.get(url)
                    location = response.headers.get("location", "")
                    if response.is_redirect and location.startswith("magnet:"):
                        return Resolved(magnet=parse_magnet(location))
                    if response.is_redirect and location:
                        url = str(response.url.join(location))
                        continue
                    break
            if response.status_code != 200:
                return Resolved(error=f"download link answered HTTP {response.status_code}")
            body = response.content
            if body.startswith(b"magnet:"):
                return Resolved(magnet=parse_magnet(body.decode().strip()))
            contents = parse_torrent(body)
            return Resolved(contents=contents, magnet=Magnet(info_hash=contents.info_hash or "", name=contents.name, trackers=contents.trackers))
        except (httpx.HTTPError, ValueError) as exc:
            if release.info_hash:
                return Resolved(magnet=Magnet(info_hash=release.info_hash.lower(), name=release.title))
            return Resolved(error=f"could not fetch the torrent: {exc}")

    async def contents(self, release: ReleaseCandidate) -> Resolved:
        """Steps 1-4: the full file list, by the least intrusive route that works."""
        resolved = await self.download_payload(release)
        if resolved.contents or not resolved.magnet or not self.qbit:
            return resolved
        magnet = resolved.magnet
        uri = build_magnet(magnet.info_hash, magnet.name, magnet.trackers or FALLBACK_TRACKERS)
        async with self._semaphore:
            try:
                existing = await self.qbit.torrent(magnet.info_hash)
                if existing is not None:
                    resolved.contents = await self._from_client(magnet.info_hash, source="qbittorrent")
                    return resolved
                if await self._supports_fetch_metadata():
                    resolved.contents = await self._fetch_metadata(uri)
                else:
                    resolved.contents = await self._probe(magnet.info_hash, uri)
            except (ServiceError, asyncio.TimeoutError) as exc:
                resolved.error = f"metadata not available: {exc}" if str(exc) else "metadata lookup timed out (dead magnet?)"
        return resolved

    async def _supports_fetch_metadata(self) -> bool:
        if self._fetch_metadata_supported is None:
            assert self.qbit is not None
            try:
                self._fetch_metadata_supported = await self.qbit.webapi_version() >= (2, 15)
            except ServiceError:
                self._fetch_metadata_supported = False
        return self._fetch_metadata_supported

    async def _fetch_metadata(self, uri: str) -> TorrentContents:
        assert self.qbit is not None
        deadline = time.monotonic() + self.probe_timeout
        while True:
            ready, payload = await self.qbit.fetch_metadata(uri)
            if ready:
                info = payload["info"]
                return TorrentContents(
                    name=info.get("name", ""),
                    info_hash=payload.get("infohash_v1") or payload.get("hash"),
                    files=[TorrentFile(path=f["path"], size=int(f["length"])) for f in info.get("files", [])]
                    or [TorrentFile(path=info.get("name", ""), size=int(info.get("length", 0)))],
                    trackers=[t["url"] for t in sorted(payload.get("trackers", []), key=lambda t: t.get("tier", 0))],
                    source="probe",
                )
            if time.monotonic() > deadline:
                raise asyncio.TimeoutError()
            await asyncio.sleep(2)

    async def _probe(self, info_hash: str, uri: str) -> TorrentContents:
        assert self.qbit is not None
        if await self.qbit.torrent(info_hash):
            # Already in the client (a real download): read it, never add or delete it.
            return await self._from_client(info_hash, source="client")
        await self.qbit.add_probe(uri, category=self.probe_category, tag=PROBE_TAG)
        try:
            deadline = time.monotonic() + self.probe_timeout
            while time.monotonic() < deadline:
                files = await self.qbit.files(info_hash)
                if files:
                    return await self._from_client(info_hash, source="probe")
                await asyncio.sleep(2)
            raise asyncio.TimeoutError()
        finally:
            try:
                if is_probe(await self.qbit.torrent(info_hash), self.probe_category):
                    await self.qbit.delete(info_hash, delete_files=True)
            except ServiceError as exc:  # pragma: no cover - best effort cleanup
                logger.warning("could not remove probe %s: %s", info_hash, exc)

    async def _from_client(self, info_hash: str, *, source: str) -> TorrentContents:
        assert self.qbit is not None
        files = await self.qbit.files(info_hash)
        props = await self.qbit.properties(info_hash)
        trackers = await self.qbit.trackers(info_hash)
        torrent = await self.qbit.torrent(info_hash) or {}
        name = torrent.get("name") or props.get("name") or ""
        return TorrentContents(
            name=name,
            info_hash=info_hash.lower(),
            # qBittorrent's file names already include the root folder for
            # multi-file torrents.
            files=[TorrentFile(path=f["name"], size=int(f["size"])) for f in files],
            trackers=[t["url"] for t in trackers if str(t.get("url", "")).startswith(("udp://", "http"))],
            source=source,  # type: ignore[arg-type]
        )

    async def cleanup_stale_probes(self) -> int:
        """Remove probes left behind by a crash. Returns how many were removed."""
        if not self.qbit:
            return 0
        tagged = await self.qbit.torrents(tag=PROBE_TAG)
        stale = [t for t in tagged if is_probe(t, self.probe_category)]
        adopted = [t for t in tagged if t not in stale]
        if stale:
            await self.qbit.delete(*[t["hash"] for t in stale], delete_files=True)
        if adopted:
            # An app grabbed the same torrent while it was being probed: it is a real
            # download now. Drop the tag, never the data.
            await self.qbit.remove_tags(PROBE_TAG, *[t["hash"] for t in adopted])
        return len(stale)


def is_probe(torrent: Optional[dict[str, Any]], probe_category: str) -> bool:
    """Only a torrent still in the probe category with nothing downloaded is a probe.

    >>> is_probe({"category": "maestarr-probe", "downloaded": 0}, "maestarr-probe")
    True
    >>> is_probe({"category": "movies", "downloaded": 0}, "maestarr-probe")
    False
    >>> is_probe({"category": "maestarr-probe", "downloaded": 5_000_000}, "maestarr-probe")
    False
    >>> is_probe(None, "maestarr-probe")
    False
    """
    if not torrent:
        return False
    return torrent.get("category") == probe_category and int(torrent.get("downloaded") or 0) < 1_000_000


async def live_swarm(resolved: list[tuple[ReleaseCandidate, Resolved]]) -> dict[str, SwarmStats]:
    """Scrape every resolvable release at once; keyed by release guid."""
    by_hash: dict[str, list[str]] = {}
    guid_hash: dict[str, str] = {}
    for release, res in resolved:
        info_hash = res.info_hash or (release.info_hash or "").lower() or None
        if not info_hash or len(info_hash) != 40:
            continue
        guid_hash[release.guid] = info_hash
        trackers = res.trackers + [t for t in FALLBACK_TRACKERS if t not in res.trackers]
        by_hash[info_hash] = trackers
    stats = await scrape_many(list(by_hash), by_hash) if by_hash else {}
    out: dict[str, SwarmStats] = {}
    for release, _ in resolved:
        info_hash = guid_hash.get(release.guid)
        live = stats.get(info_hash) if info_hash else None
        if live and live.trackers_answered:
            out[release.guid] = live
        else:
            out[release.guid] = SwarmStats(
                seeders=release.seeders or 0,
                leechers=release.leechers or 0,
                method="indexer",
                note="live scrape unavailable; indexer figure (may be stale)",
            )
    return out
