"""`serve-mcp` command — start the MCP server."""

from __future__ import annotations

import typer

from maestarr.cli.program import app


@app.command()
def serve_mcp(
    transport: str = typer.Option("stdio", help="Transport: stdio or sse"),
) -> None:
    """Start the MCP server."""
    from maestarr.server import run

    run(transport=transport)
