"""AniList GraphQL client (public data, no key) and AniList → TVDB/TMDB mapping.

AniList allows ~30 requests/minute; Maestarr calls it a handful of times per
conversation. Anime in Sonarr is keyed on TVDB ids, so AniList ids are mapped
through the community Fribb/anime-lists table (downloaded once, cached).
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

import httpx

from maestarr.clients.base import HttpService, ServiceError
from maestarr.domain import MediaRef, WatchEvent

logger = logging.getLogger(__name__)

_MEDIA_FIELDS = """
id idMal title { romaji english native } format seasonYear episodes duration
genres tags { name rank isMediaSpoiler } averageScore popularity
coverImage { large } description(asHtml: false) countryOfOrigin
"""

SEARCH_QUERY = f"""
query ($search: String, $perPage: Int) {{
  Page(perPage: $perPage) {{
    media(search: $search, type: ANIME, isAdult: false) {{ {_MEDIA_FIELDS} }}
  }}
}}"""

DISCOVER_QUERY = f"""
query ($genres: [String], $tags: [String], $perPage: Int, $minScore: Int) {{
  Page(perPage: $perPage) {{
    media(type: ANIME, isAdult: false, genre_in: $genres, tag_in: $tags,
          averageScore_greater: $minScore, sort: [SCORE_DESC, POPULARITY_DESC]) {{ {_MEDIA_FIELDS} }}
  }}
}}"""

RECOMMENDATIONS_QUERY = f"""
query ($id: Int) {{
  Media(id: $id, type: ANIME) {{
    recommendations(perPage: 10, sort: RATING_DESC) {{
      nodes {{ rating mediaRecommendation {{ {_MEDIA_FIELDS} }} }}
    }}
  }}
}}"""

USER_LIST_QUERY = """
query ($user: String) {
  MediaListCollection(userName: $user, type: ANIME, status_in: [COMPLETED, REPEATING, CURRENT]) {
    lists { entries { score(format: POINT_10_DECIMAL) status repeat
      completedAt { year month day } updatedAt
      media { id idMal seasonYear title { romaji english } } } }
  }
}"""

USER_INTEREST_QUERY = """
query ($user: String) {
  User(name: $user) { favourites { anime(perPage: 50) { nodes { id seasonYear title { romaji english } } } } }
  MediaListCollection(userName: $user, type: ANIME, status_in: [PLANNING]) {
    lists { entries { media { id seasonYear title { romaji english } } } }
  }
}"""

FRIBB_URL = "https://raw.githubusercontent.com/Fribb/anime-lists/master/anime-list-full.json"


class AniListClient(HttpService):
    name = "anilist"

    def __init__(self, cache_dir: Path, *, transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
        super().__init__("https://graphql.anilist.co", headers={"Accept": "application/json"}, transport=transport)
        self.cache_dir = cache_dir
        self._map: Optional[dict[int, dict[str, Any]]] = None

    async def query(self, query: str, **variables: Any) -> dict[str, Any]:
        data = await self.post_json("", {"query": query, "variables": variables})
        if data.get("errors"):
            raise ServiceError(self.name, "; ".join(e.get("message", "?") for e in data["errors"]))
        return data["data"]

    async def search(self, term: str, limit: int = 8) -> list[MediaRef]:
        data = await self.query(SEARCH_QUERY, search=term, perPage=limit)
        return [await self.to_ref(m) for m in data["Page"]["media"]]

    async def discover(self, genres: list[str], tags: list[str], limit: int = 20, min_score: int = 70) -> list[MediaRef]:
        data = await self.query(
            DISCOVER_QUERY, genres=genres or None, tags=tags or None, perPage=limit, minScore=min_score
        )
        return [await self.to_ref(m) for m in data["Page"]["media"]]

    async def recommendations(self, anilist_id: int) -> list[MediaRef]:
        data = await self.query(RECOMMENDATIONS_QUERY, id=anilist_id)
        nodes = ((data.get("Media") or {}).get("recommendations") or {}).get("nodes", [])
        return [await self.to_ref(n["mediaRecommendation"]) for n in nodes if n.get("mediaRecommendation")]

    async def user_history(self, user: str) -> list[WatchEvent]:
        data = await self.query(USER_LIST_QUERY, user=user)
        events: list[WatchEvent] = []
        for lst in data["MediaListCollection"]["lists"]:
            for entry in lst["entries"]:
                media = entry["media"]
                ids = await self.mapped_ids(media["id"])
                events.append(
                    WatchEvent(
                        kind="anime",
                        title=media["title"].get("english") or media["title"]["romaji"],
                        year=media.get("seasonYear"),
                        tvdb_id=ids.get("tvdb_id"),
                        tmdb_id=ids.get("tmdb_id"),
                        rating=entry.get("score") or None,
                        source="anilist",
                        play_count=1 + int(entry.get("repeat") or 0),
                    )
                )
        return events

    async def user_interest(self, user: str) -> list[WatchEvent]:
        """Favourites (strong) and the plan-to-watch list (weak)."""
        data = await self.query(USER_INTEREST_QUERY, user=user)
        favourites = ((((data.get("User") or {}).get("favourites") or {}).get("anime") or {}).get("nodes")) or []
        planning = [e["media"] for lst in (data.get("MediaListCollection") or {}).get("lists") or [] for e in lst["entries"]]
        events = []
        for media, source in [(m, "favorite") for m in favourites] + [(m, "watchlist") for m in planning]:
            ids = await self.mapped_ids(media["id"])
            events.append(WatchEvent(
                kind="anime", title=media["title"].get("english") or media["title"]["romaji"],
                year=media.get("seasonYear"), tvdb_id=ids.get("tvdb_id"), tmdb_id=ids.get("tmdb_id"),
                rating=9.5 if source == "favorite" else None, source=source,
            ))
        return events

    async def to_ref(self, media: dict[str, Any]) -> MediaRef:
        ids = await self.mapped_ids(media["id"])
        title = media["title"].get("english") or media["title"].get("romaji") or "?"
        tags = [t["name"] for t in media.get("tags") or [] if not t.get("isMediaSpoiler") and (t.get("rank") or 0) >= 60]
        score = media.get("averageScore")
        return MediaRef(
            kind="anime",
            title=title,
            year=media.get("seasonYear"),
            anilist_id=media["id"],
            tvdb_id=ids.get("tvdb_id"),
            tmdb_id=ids.get("tmdb_id"),
            imdb_id=ids.get("imdb_id"),
            overview=_strip(media.get("description")),
            genres=media.get("genres") or [],
            keywords=tags[:20],
            rating=round(score / 10, 1) if score else None,
            votes=media.get("popularity"),
            runtime_minutes=media.get("duration"),
            poster_url=(media.get("coverImage") or {}).get("large"),
        )

    async def mapped_ids(self, anilist_id: int) -> dict[str, Any]:
        mapping = await self._load_map()
        return mapping.get(anilist_id, {})

    async def _load_map(self) -> dict[int, dict[str, Any]]:
        if self._map is not None:
            return self._map
        path = self.cache_dir / "anime-list-full.json"
        stale = not path.exists() or time.time() - path.stat().st_mtime > 7 * 86400
        if stale:
            try:
                async with httpx.AsyncClient(timeout=60, transport=self._transport) as client:
                    response = await client.get(FRIBB_URL)
                    response.raise_for_status()
                    path.write_bytes(response.content)
            except httpx.HTTPError as exc:
                logger.warning("could not refresh anime id map: %s", exc)
        self._map = {}
        if path.exists():
            self._map = parse_fribb(json.loads(path.read_text()))
        return self._map


def parse_fribb(entries: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """Index the Fribb list by AniList id.

    >>> parse_fribb([{"anilist_id": 457, "tvdb_id": 79214, "themoviedb_id": {"tv": 26867},
    ...     "imdb_id": ["tt0213338"]}])[457]
    {'tvdb_id': 79214, 'tmdb_id': 26867, 'imdb_id': 'tt0213338'}
    """
    out: dict[int, dict[str, Any]] = {}
    for entry in entries:
        anilist_id = entry.get("anilist_id")
        if not anilist_id:
            continue
        tmdb = entry.get("themoviedb_id")
        if isinstance(tmdb, dict):
            tmdb = tmdb.get("tv") or tmdb.get("movie")
        imdb = entry.get("imdb_id")
        if isinstance(imdb, list):
            imdb = imdb[0] if imdb else None
        out[int(anilist_id)] = {"tvdb_id": entry.get("tvdb_id"), "tmdb_id": tmdb, "imdb_id": imdb}
    return out


def _strip(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    import re

    return re.sub(r"<[^>]+>", "", text).strip()[:600] or None
