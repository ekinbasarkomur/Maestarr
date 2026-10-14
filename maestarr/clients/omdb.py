"""OMDb client — IMDb rating and vote count for an IMDb id (free tier: 1000/day)."""

from __future__ import annotations

from typing import Any, Optional

import httpx

from maestarr.clients.base import HttpService


class OmdbClient(HttpService):
    name = "omdb"

    def __init__(self, api_key: str, *, transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
        super().__init__("https://www.omdbapi.com", params={"apikey": api_key}, transport=transport)
        self._cache: dict[str, dict[str, Any]] = {}

    async def by_imdb_id(self, imdb_id: str) -> Optional[dict[str, Any]]:
        if imdb_id in self._cache:
            return self._cache[imdb_id]
        data = await self.get_json("/", i=imdb_id, r="json")
        if not data or data.get("Response") != "True":
            return None
        self._cache[imdb_id] = data
        return data

    async def rating(self, imdb_id: str) -> tuple[Optional[float], Optional[int]]:
        """(IMDb rating 0-10, number of votes) — `(None, None)` when unknown."""
        data = await self.by_imdb_id(imdb_id)
        if not data:
            return None, None
        return parse_rating(data)


def parse_rating(data: dict[str, Any]) -> tuple[Optional[float], Optional[int]]:
    """
    >>> parse_rating({"imdbRating": "7.6", "imdbVotes": "1,234"})
    (7.6, 1234)
    >>> parse_rating({"imdbRating": "N/A", "imdbVotes": "N/A"})
    (None, None)
    """
    try:
        rating = float(data.get("imdbRating", "N/A"))
    except ValueError:
        rating = None
    votes_text = str(data.get("imdbVotes", "")).replace(",", "")
    votes = int(votes_text) if votes_text.isdigit() else None
    return rating, votes
