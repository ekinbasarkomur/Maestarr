"""Settings → Proxy: which clients go through it and which stay direct."""

from __future__ import annotations

from pydantic import SecretStr

from maestarr import net
from maestarr.config import get_settings
from maestarr.llm import proxied_http_client
from maestarr.services import Services


def settings(**extra: object):
    return get_settings().model_copy(update={
        "MAESTARR_PROXY_ENABLED": True, "MAESTARR_PROXY_TYPE": "http", "MAESTARR_PROXY_HOST": "127.0.0.1",
        "MAESTARR_PROXY_PORT": 8711, "MAESTARR_PROXY_USERNAME": "u", "MAESTARR_PROXY_PASSWORD": SecretStr("p"),
        "MAESTARR_PROXY_BYPASS": "*.example.org", "SONARR_URL": "http://127.0.0.1:8702",
        "SONARR_API_KEY": SecretStr("k"), "OMDB_API_KEY": SecretStr("k"), **extra,
    })


async def test_public_apis_use_the_proxy_and_lan_apps_do_not():
    svc = Services.from_settings(settings())
    assert net.proxy_for("https://www.omdbapi.com") == "http://u:p@127.0.0.1:8711"
    assert net.proxy_for(svc.sonarr.base_url) is None  # type: ignore[union-attr]
    assert net.proxy_for("https://tracker.example.org/announce") is None  # bypass list
    assert proxied_http_client("anthropic", None) is not None
    assert not net.udp_allowed()
    await svc.aclose()


async def test_disabled_proxy_changes_nothing():
    svc = Services.from_settings(settings(MAESTARR_PROXY_ENABLED=False))
    assert net.current() is None and net.udp_allowed()
    assert proxied_http_client("anthropic", None) is None
    await svc.aclose()


async def test_udp_direct_can_be_allowed():
    svc = Services.from_settings(settings(MAESTARR_PROXY_UDP_DIRECT=True))
    assert net.udp_allowed()
    await svc.aclose()
    net.configure(get_settings())
