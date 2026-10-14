"""Jellyfin client — watch history and "do I already have it?" lookups.

Jellyfin 10.11/12 disable the legacy `X-Emby-Token` header by default, so the
key is sent as `Authorization: MediaBrowser Token="..."`. The per-user
`/Users/{id}/Items` route is gone in 12.x; `/Items?userId=` replaces it.
Jellyfin keeps no per-play log, only `LastPlayedDate` and `PlayCount`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import httpx

from maestarr.clients.base import HttpService, ServiceError
from maestarr.domain import MediaKind, WatchEvent

_FIELDS = "ProviderIds,Genres,Overview,OriginalTitle,ProductionYear,PremiereDate,Path"


class JellyfinClient(HttpService):
    name = "jellyfin"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        user: Optional[str] = None,
        *,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        super().__init__(
            base_url,
            headers={
                "Authorization": f'MediaBrowser Token="{api_key}", Client="Maestarr", Device="server", DeviceId="maestarr", Version="1"',
                "Accept": "application/json",
            },
            # Jellyfin sorts the whole library by play date for history queries;
            # on a big library or a busy host that takes far longer than 30 s.
            timeout=httpx.Timeout(120.0, connect=10.0),
            transport=transport,
        )
        self._user_name = user
        self._user_id: Optional[str] = None

    async def system_info(self) -> dict[str, Any]:
        return await self.get_json("/System/Info")

    async def users(self) -> list[dict[str, Any]]:
        return await self.get_json("/Users")

    async def user_id(self) -> str:
        if self._user_id:
            return self._user_id
        users = await self.users()
        if not users:
            raise ServiceError(self.name, "no users found")
        chosen = None
        if self._user_name:
            chosen = next((u for u in users if u.get("Name", "").lower() == self._user_name.lower()), None)
            if chosen is None:
                raise ServiceError(self.name, f"user {self._user_name!r} not found")
        else:
            chosen = next((u for u in users if (u.get("Policy") or {}).get("IsAdministrator")), users[0])
        self._user_id = str(chosen["Id"])
        return self._user_id

    async def items(self, **params: Any) -> list[dict[str, Any]]:
        params.setdefault("userId", await self.user_id())
        params.setdefault("recursive", "true")
        params.setdefault("fields", _FIELDS)
        params.setdefault("enableUserData", "true")
        data = await self.get_json("/Items", **params)
        return (data or {}).get("Items", [])

    async def played(self, limit: int = 400) -> list[dict[str, Any]]:
        return await self.items(
            includeItemTypes="Movie,Episode",
            filters="IsPlayed",
            sortBy="DatePlayed",
            sortOrder="Descending",
            limit=limit,
        )

    async def series_items(self, ids: list[str]) -> dict[str, dict[str, Any]]:
        if not ids:
            return {}
        found = await self.items(ids=",".join(ids))
        return {str(i["Id"]): i for i in found}

    async def search(self, term: str, limit: int = 10) -> list[dict[str, Any]]:
        return await self.items(searchTerm=term, includeItemTypes="Movie,Series", limit=limit)

    async def watch_history(self, limit: int = 400) -> list[WatchEvent]:
        """Played movies and series (episodes rolled up to their show)."""
        played = await self.played(limit)
        series_ids = sorted({str(i["SeriesId"]) for i in played if i.get("Type") == "Episode" and i.get("SeriesId")})
        series = await self.series_items(series_ids)
        events: dict[str, WatchEvent] = {}
        for item in played:
            user_data = item.get("UserData") or {}
            when = _parse_date(user_data.get("LastPlayedDate"))
            if item.get("Type") == "Episode" and item.get("SeriesId"):
                show = series.get(str(item["SeriesId"]), {})
                key = f"series:{item['SeriesId']}"
                if key in events:
                    ev = events[key]
                    ev.play_count += 1
                    if when and (ev.watched_at is None or when > ev.watched_at):
                        ev.watched_at = when
                    continue
                events[key] = _event("series", show or item, when, title=item.get("SeriesName"))
            else:
                key = f"movie:{item.get('Id')}"
                ev = _event("movie", item, when)
                ev.play_count = int(user_data.get("PlayCount") or 1)
                events[key] = ev
        return sorted(
            events.values(), key=lambda e: e.watched_at.timestamp() if e.watched_at else 0.0, reverse=True
        )


def _event(kind: MediaKind, item: dict[str, Any], when: Optional[datetime], title: Optional[str] = None) -> WatchEvent:
    ids = {k.lower(): v for k, v in (item.get("ProviderIds") or {}).items()}
    user_rating = (item.get("UserData") or {}).get("Rating")
    return WatchEvent(
        kind=kind,
        title=title or item.get("Name") or "?",
        year=item.get("ProductionYear"),
        tmdb_id=_int(ids.get("tmdb")),
        tvdb_id=_int(ids.get("tvdb")),
        imdb_id=ids.get("imdb"),
        watched_at=when,
        rating=float(user_rating) if user_rating is not None else None,
        source="jellyfin",
    )


def _int(value: Any) -> Optional[int]:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        # Jellyfin sends 7 fractional digits; fromisoformat accepts up to 6.
        head, _, frac = value.rstrip("Z").partition(".")
        frac = (frac[:6]).ljust(6, "0") if frac else "000000"
        return datetime.fromisoformat(f"{head}.{frac}+00:00")
    except ValueError:
        return None
