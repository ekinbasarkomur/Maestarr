"""Prowlarr API v1 client — raw indexer search across every configured indexer.

Sonarr/Radarr's own interactive search is preferred (their results carry the
user's quality profile and custom-format scores); Prowlarr is the fallback for
free-form queries such as multi-series packs that the apps cannot map.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

import httpx

from maestarr.clients.base import HttpService
from maestarr.domain import ReleaseCandidate

# Newznab category roots.
CATEGORIES = {"movie": [2000], "series": [5000], "anime": [5070, 5000], "any": []}


class ProwlarrClient(HttpService):
    name = "prowlarr"

    def __init__(
        self, base_url: str, api_key: str, *, transport: Optional[httpx.AsyncBaseTransport] = None
    ) -> None:
        super().__init__(
            base_url,
            headers={"X-Api-Key": api_key, "Accept": "application/json"},
            timeout=httpx.Timeout(180.0, connect=10.0),
            transport=transport,
        )

    async def system_status(self) -> dict[str, Any]:
        return await self.get_json("/api/v1/system/status")

    async def indexers(self) -> list[dict[str, Any]]:
        return await self.get_json("/api/v1/indexer")

    async def search(
        self,
        query: str,
        *,
        kind: str = "any",
        indexer_ids: Optional[Sequence[int]] = None,
        limit: int = 100,
    ) -> list[ReleaseCandidate]:
        params: list[tuple[str, str]] = [("query", query), ("type", "search"), ("limit", str(limit))]
        for cat in CATEGORIES.get(kind, []):
            params.append(("categories", str(cat)))
        for idx in indexer_ids or []:
            params.append(("indexerIds", str(idx)))
        response = await self.request("GET", "/api/v1/search", params=params)
        return [release_from_prowlarr(item) for item in response.json() or []]

    async def grab(self, guid: str, indexer_id: int) -> dict[str, Any]:
        """Send a search result to Prowlarr's own download client."""
        return await self.post_json("/api/v1/search", {"guid": guid, "indexerId": indexer_id})


def release_from_prowlarr(item: dict[str, Any]) -> ReleaseCandidate:
    """Normalise one Prowlarr search result.

    >>> r = release_from_prowlarr({"guid": "x", "indexerId": 7, "indexer": "TPB", "title": "T",
    ...     "size": 10, "seeders": 5, "leechers": 1, "infoHash": "ABC", "protocol": "torrent"})
    >>> (r.app, r.indexer, r.info_hash, r.seeders)
    ('prowlarr', 'TPB', 'ABC', 5)
    """
    age_hours = item.get("ageHours")
    return ReleaseCandidate(
        app="prowlarr",
        guid=str(item.get("guid")),
        indexer_id=int(item.get("indexerId") or 0),
        indexer=str(item.get("indexer") or ""),
        title=str(item.get("title") or item.get("sortTitle") or ""),
        size=int(item.get("size") or 0),
        protocol=str(item.get("protocol") or "torrent"),
        seeders=item.get("seeders"),
        leechers=item.get("leechers"),
        age_days=round(float(age_hours) / 24.0, 1) if age_hours is not None else item.get("age"),
        download_url=item.get("downloadUrl"),
        magnet_url=item.get("magnetUrl"),
        info_hash=item.get("infoHash") or None,
        info_url=item.get("infoUrl"),
    )
