import pytest

from maestarr import __version__
from maestarr.server import mcp, ping


def test_ping_returns_liveness_string():
    assert ping() == "maestarr {} ok".format(__version__)


@pytest.mark.asyncio
async def test_ping_is_registered_as_an_mcp_tool():
    tools = await mcp.list_tools()
    assert "ping" in [tool.name for tool in tools]
