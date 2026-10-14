"""Logging setup for maestarr.

Logs go to both stderr and a rotating file under the log directory. Call
setup_logging() once at process start — from a CLI command or server startup,
never at import time.

**Bootstrap logging never depends on Settings.** The CLI root callback runs
before `.env` can be assumed valid, so `maestarr hello` and `--version` must
work when nothing is configured. The caller passes the level explicitly: INFO,
or DEBUG under `--verbose`. A long-running process that has since loaded
configuration (namely `serve`) may re-apply setup_logging() with the
configured level and directory — but an explicit `--verbose` always wins and
is never overridden by a settings value.

The log directory is still read from configuration when it is available, via a
best-effort lookup that degrades to the default rather than raising. That keeps
`MAESTARR_LOG_DIR` working for every command — including inside a container,
where the default directory is root-owned — without making a broken `.env` fatal
to a command that never needed one.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

_configured = False
_current_log_dir: Optional[Path] = None


def _configured_log_dir() -> Optional[str]:
    """Read the configured log directory, or None if configuration is unusable.

    Deliberately swallows every exception: this runs on the fast path, where a
    missing or invalid `.env` must not stop a command that does not need one.
    """
    try:
        from maestarr.config import get_settings

        return get_settings().MAESTARR_LOG_DIR or None
    except Exception:  # noqa: BLE001 — see docstring
        return None


def log_dir(override: Optional[str] = None) -> Path:
    """Return the directory log files are written to, creating it if needed.

    `override`, when given, sets the directory for this and future calls (used
    by long-running processes applying a configured log_dir). Otherwise falls
    back to configuration, then to <project_root>/logs.
    """
    global _current_log_dir
    if override is not None:
        _current_log_dir = Path(override)
    if _current_log_dir is None:
        configured = _configured_log_dir()
        _current_log_dir = (
            Path(configured)
            if configured
            else Path(__file__).resolve().parent.parent / "logs"
        )
    _current_log_dir.mkdir(parents=True, exist_ok=True)
    return _current_log_dir


def log_path() -> Path:
    """Return the path of the main log file."""
    return log_dir() / "maestarr.log"


def setup_logging(
    level: int = logging.INFO,
    log_dir_override: Optional[str] = None,
    quiet: bool = False,
) -> logging.Logger:
    """Configure root logging.

    Idempotent for handler setup — safe to call more than once; each call still
    applies `level`, so a long-running process can re-apply a different level
    after loading configuration without re-adding duplicate handlers.

    Args:
        level: effective log level (e.g. logging.INFO, logging.DEBUG).
        log_dir_override: absolute path to write logs to; only meaningful on the
            first call, since the file handler is created once.
        quiet: When True, suppress the stderr handler; file logging is unaffected.
    """
    global _configured
    root = logging.getLogger()

    if log_dir_override is not None:
        log_dir(log_dir_override)

    if _configured:
        root.setLevel(level)
        return root

    root.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        log_path(), maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    if not quiet:
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)

    # Per-request INFO lines from the HTTP stack drown everything else.
    for noisy in ("httpx", "httpcore", "aiogram.event"):
        logging.getLogger(noisy).setLevel(max(level, logging.WARNING))

    _configured = True
    return root


def get_logger(name: str) -> logging.Logger:
    """Return a module-scoped logger. Does not configure handlers."""
    return logging.getLogger(name)
