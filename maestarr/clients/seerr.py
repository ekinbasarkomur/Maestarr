"""Seerr (Overseerr / Jellyseerr) as a stand-in for TMDB.

Seerr queries TMDB with its own built-in key and exposes search, discover,
genres, keywords, details (credits, keywords, videos, external ids) and
recommendations through its API. With only a Seerr API key — no TMDB account —
Maestarr gets the same metadata. Responses are translated to TMDB's own shape
(snake_case, nested ``results``), so the rest of the code does not care which
one it talks to.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Literal, Optional

import httpx

from maestarr.clients.base import HttpService
from maestarr.clients.tmdb import TmdbClient, TmdbKind

_CAMEL = re.compile(r"(?<!^)(?=[A-Z])")

# TMDB discover parameter → Seerr's name for it.
_DISCOVER = {
    "with_genres": "genre",
    "with_keywords": "keywords",
    "with_original_language": "language",
    "sort_by": "sortBy",
    "vote_average.gte": "voteAverageGte",
    "vote_average.lte": "voteAverageLte",
    "vote_count.gte": "voteCountGte",
    "vote_count.lte": "voteCountLte",
    "with_runtime.gte": "withRuntimeGte",
    "with_runtime.lte": "withRuntimeLte",
    "primary_release_date.gte": "primaryReleaseDateGte",
    "primary_release_date.lte": "primaryReleaseDateLte",
    "first_air_date.gte": "firstAirDateGte",
    "first_air_date.lte": "firstAirDateLte",
}


def snake(value: Any) -> Any:
    """Seerr's camelCase JSON → TMDB's snake_case, recursively.

    >>> snake({"posterPath": "/p.jpg", "genreIds": [1], "credits": {"cast": [{"profilePath": None}]}})
    {'poster_path': '/p.jpg', 'genre_ids': [1], 'credits': {'cast': [{'profile_path': None}]}}
    """
    if isinstance(value, dict):
        return {_CAMEL.sub("_", k).lower(): snake(v) for k, v in value.items()}
    if isinstance(value, list):
        return [snake(v) for v in value]
    return value


def tmdb_details(raw: dict[str, Any]) -> dict[str, Any]:
    """A Seerr movie/tv payload in the shape of TMDB's details with
    ``append_to_response=keywords,credits,external_ids,videos``.

    >>> d = tmdb_details({"id": 1, "keywords": [{"id": 9, "name": "space"}], "externalIds": {"imdbId": "tt1", "tvdbId": 7},
    ...                   "relatedVideos": [{"site": "YouTube", "key": "k", "type": "Trailer"}]})
    >>> d["keywords"], d["external_ids"], d["videos"]["results"][0]["key"]
    ({'keywords': [{'id': 9, 'name': 'space'}], 'results': [{'id': 9, 'name': 'space'}]}, {'imdb_id': 'tt1', 'tvdb_id': 7}, 'k')
    """
    d = snake(raw)
    words = d.get("keywords") or []
    if isinstance(words, list):
        d["keywords"] = {"keywords": words, "results": words}
    ext = d.get("external_ids") or {}
    d["external_ids"] = {"imdb_id": ext.get("imdb_id") or d.get("imdb_id"), "tvdb_id": ext.get("tvdb_id")}
    d["videos"] = {"results": d.pop("related_videos", None) or []}
    if d.get("episode_run_time") is None and d.get("runtime"):
        d["episode_run_time"] = [d["runtime"]]
    return d


class SeerrMetadataClient(TmdbClient):
    """TmdbClient's interface, answered by Seerr."""

    name = "seerr"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        language: str = "en",
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        HttpService.__init__(
            self,
            base_url.rstrip("/") + "/api/v1",
            headers={"X-Api-Key": api_key, "Accept": "application/json"},
            transport=transport,
        )
        self.language = language
        self._genres: dict[TmdbKind, dict[int, str]] = {}
        self._genre_lock = asyncio.Lock()

    async def configuration(self) -> dict[str, Any]:
        return await self.get_json("/settings/public")

    async def genres(self, kind: TmdbKind) -> dict[int, str]:
        async with self._genre_lock:
            if kind not in self._genres:
                data = await self.get_json(f"/genres/{kind}", language=self.language)
                self._genres[kind] = {g["id"]: g["name"] for g in data or []}
        return self._genres[kind]

    async def search(self, kind: TmdbKind, query: str, year: Optional[int] = None) -> list[dict[str, Any]]:
        data = await self.get_json("/search", query=query, page=1, language=self.language)
        hits = [snake(r) for r in (data or {}).get("results", []) if r.get("mediaType") == kind]
        if year:
            dated = [h for h in hits if str(h.get("release_date") or h.get("first_air_date") or "").startswith(str(year))]
            hits = dated or hits
        return hits

    async def search_keywords(self, query: str) -> list[dict[str, Any]]:
        data = await self.get_json("/search/keyword", query=query, page=1)
        return snake((data or {}).get("results", []))

    async def details(self, kind: TmdbKind, tmdb_id: int) -> dict[str, Any]:
        raw, recs, similar = await asyncio.gather(
            self.get_json(f"/{kind}/{tmdb_id}", language=self.language),
            self.get_json(f"/{kind}/{tmdb_id}/recommendations", page=1, language=self.language),
            self.get_json(f"/{kind}/{tmdb_id}/similar", page=1, language=self.language),
        )
        d = tmdb_details(raw or {})
        d["recommendations"] = {"results": snake((recs or {}).get("results", []))}
        d["similar"] = {"results": snake((similar or {}).get("results", []))}
        return d

    async def discover(self, kind: TmdbKind, **filters: Any) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"page": 1, "language": self.language, "sortBy": "vote_average.desc"}
        for key, value in filters.items():
            if value is None or key == "include_adult":
                continue
            name = _DISCOVER.get(key)
            if name:
                # TMDB uses | for "any of"; Seerr takes a comma list.
                params[name] = str(value).replace("|", ",")
        path = "/discover/movies" if kind == "movie" else "/discover/tv"
        data = await self.get_json(path, **params)
        return snake((data or {}).get("results", []))

    async def find(self, external_id: str, source: Literal["imdb_id", "tvdb_id"]) -> dict[str, Any]:
        """Seerr has no /find; search by the id where it can, else report nothing."""
        if source == "tvdb_id":
            data = await self.get_json("/search", query=f"tvdb:{external_id}", page=1)
            hits = snake((data or {}).get("results", []))
            return {"tv_results": [h for h in hits if h.get("media_type") == "tv"], "movie_results": []}
        data = await self.get_json("/search", query=f"imdb:{external_id}", page=1)
        hits = snake((data or {}).get("results", []))
        return {
            "movie_results": [h for h in hits if h.get("media_type") == "movie"],
            "tv_results": [h for h in hits if h.get("media_type") == "tv"],
        }
