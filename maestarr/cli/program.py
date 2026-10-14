"""maestarr CLI — Typer app, root callback, and console-script entrypoint."""

from __future__ import annotations

from dataclasses import dataclass

import typer

from maestarr import APPLIED_SPECS, __version__

app = typer.Typer(
    name="maestarr",
    help="Maestarr — an AI maestro for your *arr stack: taste-aware recommendations, release judging with live swarm data, and chat control of Sonarr, Radarr, Prowlarr and qBittorrent",
    no_args_is_help=True,
    add_completion=False,
)


@dataclass
class CliContext:
    """Per-invocation shared context, built once in the root callback."""

    verbose: bool


def get_context(ctx: typer.Context) -> CliContext:
    """Read the CliContext a command's typer.Context was given by _root."""
    return ctx.obj


def _version_callback(value: bool) -> None:
    if not value:
        return
    specs = ", ".join(str(n) for n in APPLIED_SPECS) if APPLIED_SPECS else "none"
    typer.echo(f"maestarr {__version__}")
    typer.echo(f"specs applied: {specs}")
    raise typer.Exit()


@app.callback()
def _root(
    ctx: typer.Context,
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose (DEBUG) logging.",
    ),
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show version and applied specs, then exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """maestarr CLI.

    Fast-path invariant: this callback does only light, unconditional setup —
    `setup_logging()`, which is local file/stderr I/O — and builds CliContext.
    It never opens a database connection and never requires `.env` to be
    valid, so `maestarr hello` and `--version` keep working when optional
    infrastructure is unconfigured. Bootstrap logging is INFO, DEBUG under
    `--verbose`, and never reads Settings.
    """
    import logging

    from maestarr.logger import setup_logging

    setup_logging(level=logging.DEBUG if verbose else logging.INFO)
    ctx.obj = CliContext(verbose=verbose)


def main() -> None:
    """Console-script entrypoint. `pyproject.toml` points `maestarr` at
    `maestarr.cli:main`, which `cli/__init__.py` re-exports from here."""
    app()
