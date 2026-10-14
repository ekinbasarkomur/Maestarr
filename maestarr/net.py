"""Outbound proxy, configured the way Sonarr, Radarr and Prowlarr do it.

Settings → Proxy holds the type (HTTP or SOCKS5), host, port, optional
credentials, a comma-separated bypass list (exact hosts or ``*.domain``
wildcards) and "bypass for local addresses". Every outbound HTTP client asks
`proxy_for(url)` whether its target should go through the proxy, so the
metadata APIs, the AI provider, HTTP tracker scrapes and Telegram can leave
through a VPN while the *arr apps on the LAN are reached directly.

UDP tracker scrapes cannot ride an HTTP proxy; while a proxy is on they are
skipped (seeders then come from the indexer) unless the user allows direct UDP.
"""

from __future__ import annotations

import fnmatch
import ipaddress
import logging
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import quote, urlsplit

logger = logging.getLogger(__name__)

PROXY_TYPES = ("http", "socks5")


@dataclass(frozen=True)
class ProxyConfig:
    kind: str
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    bypass: tuple[str, ...] = ()
    bypass_local: bool = True
    udp_direct: bool = False

    @property
    def url(self) -> str:
        """
        >>> ProxyConfig("http", "gluetun", 8888).url
        'http://gluetun:8888'
        >>> ProxyConfig("socks5", "10.0.0.2", 1080, "me", "p@ss").url
        'socks5://me:p%40ss@10.0.0.2:1080'
        """
        auth = ""
        if self.username:
            auth = quote(self.username, safe="") + (":" + quote(self.password, safe="") if self.password else "") + "@"
        return f"{self.kind}://{auth}{self.host}:{self.port}"

    def applies_to(self, target: str) -> bool:
        """Whether `target` (a URL or a host name) should go through the proxy.

        >>> p = ProxyConfig("http", "gluetun", 8888, bypass=("*.lan", "jellyfin.example.com"))
        >>> [p.applies_to(u) for u in ("https://api.themoviedb.org/3", "http://127.0.0.1:8702",
        ...  "http://sonarr:8989", "http://nas.lan", "https://jellyfin.example.com", "udp://tracker.example:80")]
        [True, False, False, False, False, True]
        """
        host = _host(target)
        if not host:
            return False
        if self.bypass_local and is_local(host):
            return False
        return not any(_matches(host, pattern) for pattern in self.bypass)


def _host(target: str) -> str:
    parts = urlsplit(target if "://" in target else f"//{target}")
    return (parts.hostname or "").lower()


def _matches(host: str, pattern: str) -> bool:
    pattern = pattern.strip().lower()
    if not pattern:
        return False
    if "*" in pattern or "?" in pattern:
        return fnmatch.fnmatch(host, pattern)
    return host == pattern or host.endswith("." + pattern)


def is_local(host: str) -> bool:
    """Loopback, private, link-local and CGNAT/Tailscale addresses, plus names
    that only resolve on the LAN (no dot, ``.local``, ``.lan``, ``.internal``).

    >>> [is_local(h) for h in ("localhost", "sonarr", "192.168.1.5", "100.84.192.79", "nas.local", "8.8.8.8", "api.trakt.tv")]
    [True, True, True, True, True, False, False]
    """
    host = host.strip("[]").lower()
    try:
        return not ipaddress.ip_address(host).is_global
    except ValueError:
        pass
    return host == "localhost" or "." not in host or host.endswith((".local", ".lan", ".internal", ".home.arpa"))


_current: Optional[ProxyConfig] = None


def configure(settings: Any) -> Optional[ProxyConfig]:
    """Load the proxy from settings (called whenever services are rebuilt)."""
    global _current
    _current = from_settings(settings)
    return _current


def from_settings(settings: Any) -> Optional[ProxyConfig]:
    if not getattr(settings, "MAESTARR_PROXY_ENABLED", False):
        return None
    host = (settings.MAESTARR_PROXY_HOST or "").strip()
    port = settings.MAESTARR_PROXY_PORT
    if not host or not port:
        return None
    password = settings.MAESTARR_PROXY_PASSWORD
    return ProxyConfig(
        kind=settings.MAESTARR_PROXY_TYPE if settings.MAESTARR_PROXY_TYPE in PROXY_TYPES else "http",
        host=host,
        port=int(port),
        username=(settings.MAESTARR_PROXY_USERNAME or "").strip() or None,
        password=password.get_secret_value() if password is not None else None,
        bypass=tuple(p.strip() for p in (settings.MAESTARR_PROXY_BYPASS or "").split(",") if p.strip()),
        bypass_local=settings.MAESTARR_PROXY_BYPASS_LOCAL,
        udp_direct=settings.MAESTARR_PROXY_UDP_DIRECT,
    )


def current() -> Optional[ProxyConfig]:
    return _current


def proxy_for(target: str, config: Optional[ProxyConfig] = None) -> Optional[str]:
    """The proxy URL to use for `target`, or None to connect directly."""
    config = config if config is not None else _current
    if config is None or not config.applies_to(target):
        return None
    return config.url


def udp_allowed() -> bool:
    """UDP cannot go through the proxy: only scrape UDP trackers when no proxy
    is set, or the user allowed direct UDP."""
    return _current is None or _current.udp_direct
