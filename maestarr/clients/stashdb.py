"""StashDB (stash-box) GraphQL client — ADULT content metadata.

Disabled unless `STASHDB_ENABLED=true` and `STASHDB_API_KEY` are both set; the
agent never sees these tools otherwise. Every query needs an API key
(`ApiKey` header).
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

from maestarr.clients.base import HttpService, ServiceError

SEARCH_SCENES = """
query ($term: String!, $limit: Int) {
  searchScenes(term: $term, limit: $limit) {
    count
    scenes {
      id title release_date duration
      studio { name } tags { name }
      performers { performer { name } }
    }
  }
}"""

SEARCH_PERFORMERS = """
query ($term: String!, $limit: Int) {
  searchPerformers(term: $term, limit: $limit) {
    count
    performers { id name disambiguation aliases country }
  }
}"""


class StashDbClient(HttpService):
    name = "stashdb"

    def __init__(self, url: str, api_key: str, *, transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
        super().__init__(url, headers={"ApiKey": api_key, "Accept": "application/json"}, transport=transport)

    async def query(self, query: str, **variables: Any) -> dict[str, Any]:
        data = await self.post_json("", {"query": query, "variables": variables})
        if data.get("errors"):
            raise ServiceError(self.name, "; ".join(e.get("message", "?") for e in data["errors"]))
        return data["data"]

    async def search_scenes(self, term: str, limit: int = 10) -> list[dict[str, Any]]:
        data = await self.query(SEARCH_SCENES, term=term, limit=limit)
        scenes = (data.get("searchScenes") or {}).get("scenes") or []
        return [
            {
                "id": s["id"],
                "title": s.get("title"),
                "date": s.get("release_date"),
                "minutes": round((s.get("duration") or 0) / 60) or None,
                "studio": (s.get("studio") or {}).get("name"),
                "performers": [p["performer"]["name"] for p in s.get("performers") or []],
                "tags": [t["name"] for t in s.get("tags") or []][:12],
            }
            for s in scenes
        ]

    async def search_performers(self, term: str, limit: int = 10) -> list[dict[str, Any]]:
        data = await self.query(SEARCH_PERFORMERS, term=term, limit=limit)
        return (data.get("searchPerformers") or {}).get("performers") or []
