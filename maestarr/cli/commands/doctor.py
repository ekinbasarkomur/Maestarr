"""`doctor` command — which integrations are configured and reachable."""

from __future__ import annotations

import typer

from maestarr.cli.program import app


@app.command()
def doctor() -> None:
    """Check configuration and every integration; exit 1 if a configured one is down."""
    import asyncio

    from maestarr.config import get_settings
    from maestarr.services import Services

    try:
        settings = get_settings()
    except Exception as e:  # noqa: BLE001 — surfaced to the operator verbatim
        typer.echo(f"config: FAILED ({e})")
        raise typer.Exit(code=1)

    async def run() -> list:
        svc = Services.from_settings(settings)
        try:
            return await svc.status()
        finally:
            await svc.aclose()

    rows = asyncio.run(run())
    typer.echo(f"model: {settings.MAESTARR_MODEL}")
    failed = False
    for s in rows:
        if not s.configured:
            mark, info = "-", "not configured"
        elif s.ok:
            mark, info = "✓", s.version or "ok"
        else:
            mark, info, failed = "✗", s.detail or "unreachable", True
        typer.echo(f"  {mark} {s.name:<12} {info}")
    if failed:
        raise typer.Exit(code=1)
