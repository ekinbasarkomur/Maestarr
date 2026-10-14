"""`serve` command — start the HTTP server."""

from __future__ import annotations

import typer

from maestarr import __version__
from maestarr.cli.program import app


@app.command()
def serve(
    host: str = typer.Option(None, help="Bind host (default: from settings)"),
    port: int = typer.Option(None, help="Bind port (default: from settings)"),
    reload: bool = typer.Option(False, help="Auto-reload on code changes (dev only)"),
) -> None:
    """Start the HTTP server."""
    # uvicorn is imported here, not at module top level, so that
    # `maestarr hello` and `--version` stay fast.
    import logging

    import uvicorn

    from maestarr.config import get_settings
    from maestarr.logger import log_path, setup_logging

    settings = get_settings()
    # Re-apply logging now that configuration has loaded. The root callback
    # already set a bootstrap level without touching Settings; this is the
    # first point at which the configured level and directory are known.
    # `--verbose` wins: the root callback set DEBUG, and this must not undo it.
    configured_level = getattr(
        logging, settings.MAESTARR_LOG_LEVEL.upper(), logging.INFO
    )
    effective_level = min(logging.getLogger().level or logging.INFO, configured_level)
    setup_logging(
        level=effective_level,
        log_dir_override=settings.MAESTARR_LOG_DIR or None,
    )
    bind_host = host or settings.MAESTARR_HOST
    bind_port = port or settings.MAESTARR_PORT
    typer.echo(
        f"maestarr {__version__} starting on "
        f"{bind_host}:{bind_port} — log: {log_path()}"
    )
    uvicorn.run(
        "maestarr.app:app",
        host=bind_host,
        port=bind_port,
        reload=reload,
        log_level="info",
        log_config=None,  # use our logging config instead
    )
