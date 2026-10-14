"""MCP server for maestarr.

Started via `maestarr serve-mcp`. Register tools by
decorating functions with @mcp.tool() in this module.
"""

from __future__ import annotations

from typing import Literal, cast

from fastmcp import FastMCP

from maestarr import __version__

Transport = Literal["stdio", "http", "sse", "streamable-http"]

mcp: FastMCP = FastMCP("maestarr")


@mcp.tool()
def ping() -> str:
    """Return a liveness string identifying this server."""
    return f"maestarr {__version__} ok"


def run(transport: str = "stdio") -> None:
    """Run the MCP server over the given transport."""
    from maestarr.logger import setup_logging

    valid = ("stdio", "http", "sse", "streamable-http")
    if transport not in valid:
        raise ValueError(f"transport must be one of {', '.join(valid)}, got {transport!r}")

    # stdio transport uses stdout for protocol frames — keep logs off it.
    setup_logging(quiet=(transport == "stdio"))
    mcp.run(transport=cast(Transport, transport))


def main() -> None:
    run()


if __name__ == "__main__":
    main()
