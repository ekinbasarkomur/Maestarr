"""Shared async HTTP plumbing for every external service.

Each client owns one `httpx.AsyncClient`, created lazily so constructing a
client never does I/O, and closed by `Services.aclose()` on shutdown.
Failures surface as `ServiceError`, which tools turn into a readable message
for the model instead of a stack trace.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class ServiceError(RuntimeError):
    """A call to an external service failed in a way worth reporting."""

    def __init__(self, service: str, message: str, status: Optional[int] = None):
        self.service = service
        self.status = status
        super().__init__(f"{service}: {message}" + (f" (HTTP {status})" if status else ""))


class HttpService:
    """Base class: one base URL, default headers, JSON helpers."""

    name: str = "service"

    def __init__(
        self,
        base_url: str,
        *,
        headers: Optional[dict[str, str]] = None,
        params: Optional[dict[str, str]] = None,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._headers = headers or {}
        self._params = params or {}
        self._timeout = timeout
        self._transport = transport
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self._headers,
                params=self._params,
                timeout=self._timeout,
                transport=self._transport,
                follow_redirects=True,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self.client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise ServiceError(self.name, f"timed out calling {path}") from exc
        except httpx.HTTPError as exc:
            raise ServiceError(self.name, f"cannot reach {self.base_url}: {exc}") from exc
        if response.status_code >= 400:
            raise ServiceError(self.name, _error_text(response), response.status_code)
        return response

    async def get_json(self, path: str, **params: Any) -> Any:
        clean = {k: v for k, v in params.items() if v is not None}
        response = await self.request("GET", path, params=clean)
        return response.json() if response.content else None

    async def post_json(self, path: str, body: Any = None, **params: Any) -> Any:
        clean = {k: v for k, v in params.items() if v is not None}
        response = await self.request("POST", path, json=body, params=clean)
        return response.json() if response.content else None

    async def put_json(self, path: str, body: Any = None, **params: Any) -> Any:
        clean = {k: v for k, v in params.items() if v is not None}
        response = await self.request("PUT", path, json=body, params=clean)
        return response.json() if response.content else None

    async def delete(self, path: str, **params: Any) -> None:
        clean = {k: v for k, v in params.items() if v is not None}
        await self.request("DELETE", path, params=clean)


def _error_text(response: httpx.Response) -> str:
    """Pull a human message out of an error response (arr apps send JSON)."""
    try:
        data = response.json()
    except ValueError:
        return response.text[:300] or response.reason_phrase
    if isinstance(data, dict):
        for key in ("message", "errorMessage", "error", "status_message", "Error"):
            if data.get(key):
                return str(data[key])[:300]
    if isinstance(data, list) and data and isinstance(data[0], dict):
        msgs = [str(d.get("errorMessage") or d.get("message") or d) for d in data[:3]]
        return "; ".join(msgs)[:300]
    return str(data)[:300]
