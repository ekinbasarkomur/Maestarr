"""StashDB (stash-box) GraphQL client — ADULT content metadata.

Disabled unless `STASHDB_ENABLED=true` and `STASHDB_API_KEY` are both set; the
agent never sees these tools otherwise. Every query needs an API key
(`ApiKey` header).
"""

from __future__ import annotations

import re
from typing import Any, Optional

import httpx

from maestarr.clients.base import HttpService, ServiceError

SCENE_FIELDS = """
      id title release_date duration details
      studio { id name } tags { name }
      performers { performer { id name } }
      images { url width height }"""

SEARCH_SCENES = """
query ($term: String!, $limit: Int) {
  searchScenes(term: $term, limit: $limit) { scenes { %s } }
}""" % SCENE_FIELDS

QUERY_SCENES = """
query ($input: SceneQueryInput!) {
  queryScenes(input: $input) { count scenes { %s } }
}""" % SCENE_FIELDS

_UUID = re.compile(r"[0-9a-fA-F-]{36}")
FIND_SCENE = """
query ($id: ID!) { findScene(id: $id) { %s } }""" % SCENE_FIELDS

FIND_SCENE_FULL = """
query ($id: ID!) { findScene(id: $id) {
  id title release_date duration details director code
  studio { name } tags { name }
  urls { url site { name } }
  images { url width height }
  performers { as performer { id name gender images { url width height } } }
} }"""

IMAGE_SIZE = 640  # stash-box resizes on request; the originals are up to 6K

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
        return [scene_out(s) for s in (data.get("searchScenes") or {}).get("scenes") or []]

    async def query_scenes(
        self,
        *,
        studios: Optional[list[str]] = None,
        performers: Optional[list[str]] = None,
        sort: str = "DATE",
        per_page: int = 20,
    ) -> list[dict[str, Any]]:
        """Newest (or trending) scenes, optionally from given studio/performer ids."""
        criteria: dict[str, Any] = {"sort": sort, "direction": "DESC", "page": 1, "per_page": per_page}
        if studios:
            criteria["studios"] = {"value": studios, "modifier": "INCLUDES"}
        if performers:
            criteria["performers"] = {"value": performers, "modifier": "INCLUDES"}
        data = await self.query(QUERY_SCENES, input=criteria)
        return [scene_out(s) for s in (data.get("queryScenes") or {}).get("scenes") or []]

    async def scene(self, scene_id: str) -> Optional[dict[str, Any]]:
        data = await self.query(FIND_SCENE, id=scene_id)
        found = data.get("findScene")
        return scene_out(found) if found else None

    async def scene_full(self, scene_id: str) -> Optional[dict[str, Any]]:
        """One scene with everything the details popup shows."""
        found = (await self.query(FIND_SCENE_FULL, id=scene_id)).get("findScene")
        if not found:
            return None
        images = sorted(found.get("images") or [], key=lambda i: -(i.get("width") or 0))
        landscape = [i for i in images if (i.get("width") or 0) >= (i.get("height") or 0)] or images

        def face(p: dict[str, Any]) -> Optional[str]:
            pics = p.get("images") or []
            return f"{pics[0]['url']}?size=300" if pics else None

        return {
            "id": found["id"],
            "title": found.get("title"),
            "date": found.get("release_date"),
            "year": int(found["release_date"][:4]) if found.get("release_date") else None,
            "runtime": round((found.get("duration") or 0) / 60) or None,
            "overview": found.get("details"),
            "studio": (found.get("studio") or {}).get("name"),
            "director": found.get("director"),
            "code": found.get("code"),
            "tags": [t["name"] for t in found.get("tags") or []][:24],
            "backdrop": f"{landscape[0]['url']}?size=1280" if landscape else None,
            "poster": f"{landscape[0]['url']}?size={IMAGE_SIZE}" if landscape else None,
            "cast": [
                {"name": p["performer"]["name"], "role": p.get("as"), "image": face(p["performer"])}
                for p in found.get("performers") or []
            ],
            "links": [{"site": (u.get("site") or {}).get("name"), "url": u.get("url")} for u in found.get("urls") or []][:4],
            "genres": [],
            "ratings": [],
        }

    async def performer_genders(self, ids: list[str]) -> dict[str, str]:
        """Gender of each performer id, in one aliased request."""
        ids = [pid for pid in ids if _UUID.fullmatch(pid)]
        if not ids:
            return {}
        fields = " ".join(f'p{i}: findPerformer(id: "{pid}") {{ id gender }}' for i, pid in enumerate(ids))
        data = await self.query(f"query {{ {fields} }}")
        return {p["id"]: p.get("gender") or "" for p in data.values() if p}

    async def search_performers(self, term: str, limit: int = 10) -> list[dict[str, Any]]:
        data = await self.query(SEARCH_PERFORMERS, term=term, limit=limit)
        return (data.get("searchPerformers") or {}).get("performers") or []


def scene_out(s: dict[str, Any]) -> dict[str, Any]:
    """One scene in the shape the agent and the UI share.

    >>> scene_out({"id": "a", "title": "T", "duration": 1500, "images": [{"url": "https://x/i/1"}],
    ...            "performers": [{"performer": {"id": "p", "name": "N"}}], "studio": {"id": "s", "name": "S"}})["image"]
    'https://x/i/1?size=640'
    """
    images = s.get("images") or []
    landscape = [i for i in images if (i.get("width") or 0) >= (i.get("height") or 0)] or images
    studio = s.get("studio") or {}
    return {
        "id": s["id"],
        "title": s.get("title"),
        "date": s.get("release_date"),
        "minutes": round((s.get("duration") or 0) / 60) or None,
        "studio": studio.get("name"),
        "studio_id": studio.get("id"),
        "performers": [p["performer"]["name"] for p in s.get("performers") or []],
        "performer_ids": [p["performer"]["id"] for p in s.get("performers") or []],
        "tags": [t["name"] for t in s.get("tags") or []][:12],
        "overview": (s.get("details") or "")[:400] or None,
        "image": f"{landscape[0]['url']}?size={IMAGE_SIZE}" if landscape else None,
    }
