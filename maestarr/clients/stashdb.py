"""StashDB (stash-box) GraphQL client — ADULT content metadata.

Disabled unless `STASHDB_ENABLED=true` and `STASHDB_API_KEY` are both set; the
agent never sees these tools otherwise. Every query needs an API key
(`ApiKey` header).
"""

from __future__ import annotations

import json
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
        tags: Optional[list[str]] = None,
        exclude_tags: Optional[list[str]] = None,
        text: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        favorites: Optional[str] = None,
        sort: str = "DATE",
        direction: str = "DESC",
        page: int = 1,
        per_page: int = 20,
    ) -> list[dict[str, Any]]:
        """Scenes matching the given ids and filters (studios/performers match any;
        tags must all match). `favorites` is PERFORMER, STUDIO or ALL."""
        criteria: dict[str, Any] = {"sort": sort, "direction": direction, "page": page, "per_page": per_page}
        if studios:
            criteria["studios"] = {"value": studios, "modifier": "INCLUDES"}
        if performers:
            criteria["performers"] = {"value": performers, "modifier": "INCLUDES"}
        if tags:
            criteria["tags"] = {"value": tags, "modifier": "INCLUDES_ALL"}
        elif exclude_tags:  # one tag criterion only; with includes, excludes are filtered afterwards
            criteria["tags"] = {"value": exclude_tags, "modifier": "EXCLUDES"}
        if text:
            criteria["text"] = text
        if date_from and date_to:
            # stash-box takes one date criterion; the upper bound is applied afterwards.
            criteria["date"] = {"value": date_from, "modifier": "GREATER_THAN"}
        elif date_from:
            criteria["date"] = {"value": date_from, "modifier": "GREATER_THAN"}
        elif date_to:
            criteria["date"] = {"value": date_to, "modifier": "LESS_THAN"}
        if favorites:
            criteria["favorites"] = favorites
        data = await self.query(QUERY_SCENES, input=criteria)
        return [scene_out(s) for s in (data.get("queryScenes") or {}).get("scenes") or []]

    async def favorite_performers(self, limit: int = 50) -> list[dict[str, Any]]:
        """Performers the key's owner marked as favourites on StashDB."""
        data = await self.query(
            "query ($n: Int) { queryPerformers(input: {is_favorite: true, per_page: $n}) "
            "{ performers { id name gender } } }", n=limit)
        return (data.get("queryPerformers") or {}).get("performers") or []

    async def favorite_studios(self, limit: int = 50) -> list[dict[str, Any]]:
        data = await self.query(
            "query ($n: Int) { queryStudios(input: {is_favorite: true, per_page: $n}) { studios { id name } } }", n=limit)
        return (data.get("queryStudios") or {}).get("studios") or []

    async def search_tags(self, term: str, limit: int = 10) -> list[dict[str, Any]]:
        data = await self.query("query ($t: String!, $n: Int) { searchTag(term: $t, limit: $n) { id name } }", t=term, n=limit)
        return data.get("searchTag") or []

    async def search_studios(self, term: str, limit: int = 10) -> list[dict[str, Any]]:
        data = await self.query(
            "query ($t: String!, $n: Int) { searchStudio(term: $t, limit: $n) { id name } "
            "queryStudios(input: {name: $t, per_page: $n}) { studios { id name } } }", t=term, n=limit)
        seen: dict[str, dict[str, Any]] = {}
        for st in (data.get("searchStudio") or []) + ((data.get("queryStudios") or {}).get("studios") or []):
            seen.setdefault(st["id"], st)
        return list(seen.values())[:limit]

    async def tag_id(self, name: str) -> Optional[dict[str, Any]]:
        data = await self.query("query ($n: String!) { findTagOrAlias(name: $n) { id name } }", n=name)
        return data.get("findTagOrAlias")

    async def tag_categories(self, names: list[str]) -> dict[str, tuple[str, str]]:
        """(category, group) of each tag name, in one aliased request."""
        if not names:
            return {}
        fields = " ".join(f"t{i}: findTagOrAlias(name: {json.dumps(n)}) {{ name category {{ name group }} }}"
                          for i, n in enumerate(names))
        data = await self.query(f"query {{ {fields} }}")
        out: dict[str, tuple[str, str]] = {}
        for n, t in zip(names, (data.get(f"t{i}") for i in range(len(names)))):
            cat = (t or {}).get("category") or {}
            out[n] = (cat.get("name") or "", cat.get("group") or "")
        return out

    async def scenes_by_ids(self, ids: list[str]) -> list[dict[str, Any]]:
        """Several scenes in one aliased request."""
        ids = [i for i in ids if _UUID.fullmatch(i)]
        if not ids:
            return []
        fields = " ".join(f's{i}: findScene(id: "{sid}") {{ {SCENE_FIELDS} }}' for i, sid in enumerate(ids))
        data = await self.query(f"query {{ {fields} }}")
        return [scene_out(sc) for sc in data.values() if sc]

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
        "tags": [t["name"] for t in s.get("tags") or []],  # all of them: search filters on them
        "overview": (s.get("details") or "")[:400] or None,
        "image": f"{landscape[0]['url']}?size={IMAGE_SIZE}" if landscape else None,
    }
