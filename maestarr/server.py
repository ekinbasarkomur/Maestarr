"""MCP server — the agent's toolset exposed to any MCP client.

The SAME `FunctionToolset` the chat agent uses is bridged onto the official
MCP SDK's low-level server, so names, descriptions, JSON schemas and argument
validation are identical in both places. Approval is the MCP client's job
there: state-changing tools are marked `destructiveHint` and every call is
treated as approved (the client already asked its user).

Transports: stdio (`maestarr serve-mcp`) and streamable HTTP, mounted at
`/mcp` inside the main FastAPI app.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import mcp.types as mt
from mcp.server.lowlevel import Server
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from maestarr import __version__
from maestarr.agent.tools import WRITE_TOOLS, toolset
from maestarr.services import Services, get_services

logger = logging.getLogger(__name__)

INSTRUCTIONS = (
    "Maestarr controls a home media stack (Sonarr, Radarr, Whisparr, Prowlarr, qBittorrent, "
    "Jellyfin) and recommends titles from the user's history. Use judge_releases before "
    "grab_release; destructive tools change or delete things in the user's library."
)


def _context(svc: Services) -> RunContext[Services]:
    # Tools never read ctx.model; a placeholder satisfies RunContext.
    return RunContext(deps=svc, model=TestModel(), usage=RunUsage(), tool_call_approved=True)


async def list_tool_defs(svc: Services) -> list[mt.Tool]:
    tools = await toolset.get_tools(_context(svc))
    out: list[mt.Tool] = []
    for name, tool in sorted(tools.items()):
        d = tool.tool_def
        out.append(
            mt.Tool(
                name=name,
                description=d.description or "",
                input_schema=d.parameters_json_schema,
                annotations=mt.ToolAnnotations(
                    read_only_hint=name not in WRITE_TOOLS,
                    destructive_hint=name in WRITE_TOOLS,
                ),
            )
        )
    return out


async def call(svc: Services, name: str, arguments: Optional[dict[str, Any]]) -> tuple[bool, str]:
    """Run one tool; returns (is_error, json text)."""
    ctx = _context(svc)
    tools = await toolset.get_tools(ctx)
    tool = tools.get(name)
    if tool is None:
        return True, json.dumps({"error": f"unknown or unavailable tool {name!r}"})
    try:
        args = tool.args_validator.validate_python(arguments or {})
        result = await toolset.call_tool(name, args, ctx, tool)
    except ModelRetry as exc:
        return True, json.dumps({"error": exc.message})
    except Exception as exc:  # noqa: BLE001 — surface to the client, never crash the server
        logger.exception("mcp tool %s failed", name)
        return True, json.dumps({"error": f"{type(exc).__name__}: {exc}"})
    return False, json.dumps(result, default=str, ensure_ascii=False)


def build_server(svc: Optional[Services] = None) -> Server[Any]:
    def services() -> Services:
        return svc or get_services()

    async def on_list_tools(ctx: Any, params: Any) -> mt.ListToolsResult:
        return mt.ListToolsResult(tools=await list_tool_defs(services()))

    async def on_call_tool(ctx: Any, params: mt.CallToolRequestParams) -> mt.CallToolResult:
        is_error, text = await call(services(), params.name, params.arguments)
        return mt.CallToolResult(content=[mt.TextContent(type="text", text=text)], is_error=is_error)

    return Server(
        "maestarr",
        version=__version__,
        instructions=INSTRUCTIONS,
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )


def run(transport: str = "stdio") -> None:
    """Run over stdio (for Claude Desktop/Code). HTTP is served by `maestarr serve` at /mcp."""
    import anyio

    from maestarr.logger import setup_logging

    if transport != "stdio":
        raise ValueError("only stdio here — the HTTP transport lives at /mcp in `maestarr serve`")
    setup_logging(quiet=True)  # stdout carries protocol frames

    async def main() -> None:
        from mcp.server.stdio import stdio_server

        server = build_server()
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    anyio.run(main)


def main() -> None:
    run()


if __name__ == "__main__":
    main()
