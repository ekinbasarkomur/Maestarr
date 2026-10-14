"""Import every command module so their @app.command() decorators fire.

This is the Typer-idiomatic stand-in for a centralized command register:
importing this package registers every command on the shared `app` from
`program.py`. When you add a command module, add it to this import list —
that is the only registration step.
"""

from __future__ import annotations

from maestarr.cli.commands import (  # noqa: F401
    doctor,
    serve,
    serve_mcp,
    tools,
)
