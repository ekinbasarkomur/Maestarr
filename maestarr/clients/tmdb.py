"""TMDB API v3 client — search, discovery, keywords and details.

Auth accepts either a v3 API key (sent as `api_key`) or a v4 read-access token
(a JWT, sent as a Bearer header); both reach the v3 endpoints. TMDB's limit is
roughly 40 requests/second, far above what a chat needs.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal, Optional

import httpx

from maestarr.clients.base import HttpService
from maestarr.domain import MediaKind, MediaRef

IMAGE_BASE = "https://image.tmdb.org/t/p/w342"
TmdbKind = Literal["movie", "tv"]


def tmdb_kind(kind: MediaKind) -> TmdbKind:
    return "movie" if kind == "movie" else "tv"


class TmdbClient(HttpService):
    name = "tmdb"

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.themoviedb.org/3",
        language: str = "en-US",
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        is_token = "." in api_key and len(api_key) > 60
        super().__init__(
            base_url,
            headers={"Authorization": f"Bearer {api_key}"} if is_token else {"Accept": "application/json"},
            params={} if is_token else {"api_key": api_key},
            transport=transport,
        )
        self.language = language
        self._genres: dict[TmdbKind, dict[int, str]] = {}
        self._genre_lock = asyncio.Lock()

    async def configuration(self) -> dict[str, Any]:
        return await self.get_json("/configuration")

    async def genres(self, kind: TmdbKind) -> dict[int, str]:
        async with self._genre_lock:
            if kind not in self._genres:
                data = await self.get_json(f"/genre/{kind}/list", language=self.language)
                self._genres[kind] = {g["id"]: g["name"] for g in data.get("genres", [])}
        return self._genres[kind]

    async def genre_ids(self, kind: TmdbKind, names: list[str]) -> list[int]:
        lookup = {name.lower(): gid for gid, name in (await self.genres(kind)).items()}
        return [lookup[n.lower()] for n in names if n.lower() in lookup]

    async def search(self, kind: TmdbKind, query: str, year: Optional[int] = None) -> list[dict[str, Any]]:
        year_key = "year" if kind == "movie" else "first_air_date_year"
        data = await self.get_json(
            f"/search/{kind}", query=query, include_adult="false", language=self.language, **{year_key: year}
        )
        return data.get("results", [])

    async def search_keywords(self, query: str) -> list[dict[str, Any]]:
        data = await self.get_json("/search/keyword", query=query)
        return data.get("results", [])

    async def details(self, kind: TmdbKind, tmdb_id: int) -> dict[str, Any]:
        return await self.get_json(
            f"/{kind}/{tmdb_id}",
            language=self.language,
            append_to_response="keywords,credits,external_ids,recommendations,similar,videos",
        )

    async def discover(self, kind: TmdbKind, **filters: Any) -> list[dict[str, Any]]:
        params = {"include_adult": "false", "language": self.language, "sort_by": "vote_average.desc"}
        params.update({k: v for k, v in filters.items() if v is not None})
        data = await self.get_json(f"/discover/{kind}", **params)
        return data.get("results", [])

    async def search_people(self, query: str) -> list[dict[str, Any]]:
        data = await self.get_json("/search/person", query=query, include_adult="false", language=self.language)
        return data.get("results", [])

    async def person_credits(self, person_id: int) -> dict[str, Any]:
        """{cast: [...], crew: [...]} across movies and series (media_type on each)."""
        return await self.get_json(f"/person/{person_id}/combined_credits", language=self.language)

    async def find(self, external_id: str, source: Literal["imdb_id", "tvdb_id"]) -> dict[str, Any]:
        return await self.get_json(f"/find/{external_id}", external_source=source)

    async def to_ref(self, kind: TmdbKind, item: dict[str, Any], *, anime: bool = False) -> MediaRef:
        """Map a search/discover result (genre_ids) or a details payload (genres)."""
        names = await self.genres(kind)
        genres = [g["name"] for g in item.get("genres", [])] or [
            names[g] for g in item.get("genre_ids", []) if g in names
        ]
        kw_block = item.get("keywords") or {}
        keywords = [k["name"] for k in kw_block.get("keywords", kw_block.get("results", []))]
        date = item.get("release_date") or item.get("first_air_date") or ""
        external = item.get("external_ids") or {}
        runtime = item.get("runtime") or (item.get("episode_run_time") or [None])[0]
        return MediaRef(
            kind="movie" if kind == "movie" else ("anime" if anime else "series"),
            title=item.get("title") or item.get("name") or "?",
            year=int(date[:4]) if date[:4].isdigit() else None,
            tmdb_id=item.get("id"),
            tvdb_id=external.get("tvdb_id"),
            imdb_id=item.get("imdb_id") or external.get("imdb_id"),
            overview=item.get("overview") or None,
            genres=genres,
            keywords=keywords[:25],
            rating=item.get("vote_average"),
            votes=item.get("vote_count"),
            original_language=item.get("original_language"),
            runtime_minutes=runtime,
            poster_url=f"{IMAGE_BASE}{item['poster_path']}" if item.get("poster_path") else None,
        )


def credits_people(details: dict[str, Any], cast_top: int = 5) -> list[str]:
    """Top-billed cast plus directors/creators from a details payload.

    >>> credits_people({"credits": {"cast": [{"name": "A", "order": 1}, {"name": "B", "order": 0}],
    ...     "crew": [{"name": "D", "job": "Director"}, {"name": "X", "job": "Editor"}]}})
    ['B', 'A', 'D']
    """
    credits = details.get("credits") or {}
    cast = sorted(credits.get("cast", []), key=lambda c: c.get("order", 99))[:cast_top]
    crew = [c for c in credits.get("crew", []) if c.get("job") in ("Director", "Creator")]
    creators = details.get("created_by") or []
    names = [c["name"] for c in cast] + [c["name"] for c in crew] + [c["name"] for c in creators]
    return list(dict.fromkeys(names))
