"""maestarr CLI package.

Re-exports `app` and `main` so the console script `maestarr.cli:main`
(registered in pyproject.toml) resolves even though `maestarr.cli` is a
package rather than a single module.
"""

from __future__ import annotations

from maestarr.cli import commands as _commands  # noqa: F401 — fires @app.command() registration
from maestarr.cli.program import app, main

__all__ = ["app", "main"]
