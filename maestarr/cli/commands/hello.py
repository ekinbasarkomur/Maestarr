"""`hello` command."""

from __future__ import annotations

import typer

from maestarr.cli.program import app


@app.command()
def hello() -> None:
    """Print a greeting."""
    typer.echo("Hello, world!")
