"""qBittorrent Web UI API v2 client.

Authentication is a session cookie (`SID`) from `/api/v2/auth/login`. The
client logs in lazily and once more on a 403, so a qBittorrent restart is
transparent. When qBittorrent runs with "Bypass authentication for clients on
localhost" and no credentials are configured, login is skipped.

qBittorrent 5 renamed pause/resume to stop/start; both spellings are tried.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional, Sequence

import httpx

from maestarr.clients.base import HttpService, ServiceError


class QBittorrentClient(HttpService):
    name = "qbittorrent"

    def __init__(
        self,
        base_url: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        *,
        host_header: Optional[str] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        headers = {"Referer": base_url.rstrip("/")}
        if host_header:
            # qBittorrent's CSRF check compares Referer/Origin with Host.
            headers["Host"] = host_header
            headers["Referer"] = f"http://{host_header}"
        super().__init__(base_url, headers=headers, transport=transport)
        self._username = username
        self._password = password
        self._logged_in = False
        self._login_lock = asyncio.Lock()

    async def _login(self) -> None:
        async with self._login_lock:
            if self._logged_in:
                return
            if not self._username:
                self._logged_in = True  # localhost bypass / no auth configured
                return
            response = await super().request(
                "POST",
                "/api/v2/auth/login",
                data={"username": self._username, "password": self._password or ""},
            )
            # qBittorrent < 5.2 answers "Ok."; 5.2+ answers 204 with an empty
            # body. Only "Fails." (or no session cookie) means a bad login.
            if response.text.strip() == "Fails." or "SID" not in self.client.cookies and not response.cookies:
                raise ServiceError(self.name, "login failed (wrong credentials or IP banned)")
            self._logged_in = True

    async def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        await self._login()
        try:
            return await super().request(method, path, **kwargs)
        except ServiceError as exc:
            if exc.status != 403 or not self._username:
                raise
            self._logged_in = False
            await self._login()
            return await super().request(method, path, **kwargs)

    # --- app -------------------------------------------------------------

    async def version(self) -> str:
        return (await self.request("GET", "/api/v2/app/version")).text.strip()

    async def preferences(self) -> dict[str, Any]:
        return await self.get_json("/api/v2/app/preferences")

    async def transfer_info(self) -> dict[str, Any]:
        return await self.get_json("/api/v2/transfer/info")

    async def categories(self) -> dict[str, Any]:
        return await self.get_json("/api/v2/torrents/categories")

    # --- torrents --------------------------------------------------------

    async def torrents(
        self,
        *,
        hashes: Optional[Sequence[str]] = None,
        category: Optional[str] = None,
        filter: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        return await self.get_json(
            "/api/v2/torrents/info",
            hashes="|".join(h.lower() for h in hashes) if hashes else None,
            category=category,
            filter=filter,
            tag=tag,
        )

    async def torrent(self, info_hash: str) -> Optional[dict[str, Any]]:
        found = await self.torrents(hashes=[info_hash])
        return found[0] if found else None

    async def properties(self, info_hash: str) -> dict[str, Any]:
        return await self.get_json("/api/v2/torrents/properties", hash=info_hash.lower())

    async def files(self, info_hash: str) -> list[dict[str, Any]]:
        return await self.get_json("/api/v2/torrents/files", hash=info_hash.lower())

    async def trackers(self, info_hash: str) -> list[dict[str, Any]]:
        return await self.get_json("/api/v2/torrents/trackers", hash=info_hash.lower())

    async def add(
        self,
        *,
        urls: Optional[Sequence[str]] = None,
        torrent_bytes: Optional[bytes] = None,
        category: Optional[str] = None,
        tags: Optional[Sequence[str]] = None,
        stopped: bool = False,
        savepath: Optional[str] = None,
        sequential: bool = False,
    ) -> None:
        data: dict[str, str] = {}
        if urls:
            data["urls"] = "\n".join(urls)
        if category:
            data["category"] = category
        if tags:
            data["tags"] = ",".join(tags)
        if savepath:
            data["savepath"] = savepath
        if stopped:
            # qBittorrent >= 5 reads `stopped`, older versions `paused`.
            data["stopped"] = "true"
            data["paused"] = "true"
        if sequential:
            data["sequentialDownload"] = "true"
        files = {"torrents": ("upload.torrent", torrent_bytes, "application/x-bittorrent")} if torrent_bytes else None
        response = await self.request("POST", "/api/v2/torrents/add", data=data, files=files)
        text = response.text.strip()
        if text.startswith("Fails"):
            raise ServiceError(self.name, "torrent was rejected (duplicate or invalid)")

    async def webapi_version(self) -> tuple[int, ...]:
        text = (await self.request("GET", "/api/v2/app/webapiVersion")).text.strip()
        return tuple(int(p) for p in text.split(".") if p.isdigit())

    async def fetch_metadata(self, source: str) -> tuple[bool, dict[str, Any]]:
        """qBittorrent >= 5.2: resolve a magnet/URL's metadata WITHOUT adding it.

        Returns `(ready, payload)`; while metadata is still being fetched the
        API answers 202 and `ready` is False — call again to poll.
        """
        response = await self.request("POST", "/api/v2/torrents/fetchMetadata", data={"source": source})
        payload = response.json() if response.content else {}
        return response.status_code == 200 and bool(payload.get("info")), payload

    async def add_probe(self, magnet: str, *, category: str, tag: str) -> None:
        """Older qBittorrent: add a magnet that stops itself once metadata arrives.

        A torrent added *stopped* never fetches metadata, so it is added
        running with `stopCondition=MetadataReceived` (qBittorrent pauses it the
        moment metadata is in, before any piece is downloaded) and `forced` so
        queue limits cannot park it.
        """
        data = {
            "urls": magnet,
            "category": category,
            "tags": tag,
            "stopCondition": "MetadataReceived",
            "forced": "true",
            "autoTMM": "false",
        }
        await self.request("POST", "/api/v2/torrents/add", data=data)

    async def set_file_priority(self, info_hash: str, file_ids: Sequence[int], priority: int) -> None:
        """priority: 0 = do not download, 1 = normal, 6 = high, 7 = maximal."""
        if not file_ids:
            return
        await self.request(
            "POST",
            "/api/v2/torrents/filePrio",
            data={"hash": info_hash.lower(), "id": "|".join(str(i) for i in file_ids), "priority": str(priority)},
        )

    async def delete(self, *hashes: str, delete_files: bool = False) -> None:  # type: ignore[override]
        await self.request(
            "POST",
            "/api/v2/torrents/delete",
            data={"hashes": "|".join(h.lower() for h in hashes), "deleteFiles": str(delete_files).lower()},
        )

    async def stop(self, *hashes: str) -> None:
        await self._either("/api/v2/torrents/stop", "/api/v2/torrents/pause", hashes)

    async def start(self, *hashes: str) -> None:
        await self._either("/api/v2/torrents/start", "/api/v2/torrents/resume", hashes)

    async def reannounce(self, *hashes: str) -> None:
        await self.request("POST", "/api/v2/torrents/reannounce", data={"hashes": "|".join(h.lower() for h in hashes)})

    async def _either(self, new: str, old: str, hashes: Sequence[str]) -> None:
        data = {"hashes": "|".join(h.lower() for h in hashes)}
        try:
            await self.request("POST", new, data=data)
        except ServiceError as exc:
            if exc.status != 404:
                raise
            await self.request("POST", old, data=data)
