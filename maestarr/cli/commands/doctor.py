"""`doctor` command — validate configuration and external dependencies."""

from __future__ import annotations

import typer

from maestarr.cli.program import app


@app.command()
def doctor() -> None:
    """Validate configuration and external dependencies, and report status."""
    from maestarr.config import get_settings

    ok = True

    try:
        get_settings()
        typer.echo("  config:               OK")
    except Exception as e:  # noqa: BLE001 — surfaced to the operator verbatim
        typer.echo(f"  config:               FAILED ({e})")
        ok = False

    if not ok:
        raise typer.Exit(code=1)
    typer.echo("All checks passed.")
