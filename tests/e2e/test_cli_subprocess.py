"""End-to-end: the installed console script, run as a real subprocess.

`CliRunner` (tests/unit/test_cli.py) invokes the Typer app in-process, which
proves the command logic but not the packaging. This layer proves the other
half: that `pip install -e .` actually put a working `maestarr` on PATH, that
`maestarr.cli:main` resolves now that `cli` is a package, and that the
fast-path commands run without any infrastructure configured.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from maestarr import __version__


def _console_script() -> str | None:
    """Locate the installed `maestarr` script.

    Look beside the running interpreter FIRST. The documented way to run this
    suite is `.venv/bin/python -m pytest`, which does not put `.venv/bin` on
    PATH — a bare `shutil.which` would skip this whole file exactly when it is
    supposed to run.
    """
    candidate = Path(sys.executable).parent / "maestarr"
    if candidate.exists():
        return str(candidate)
    return shutil.which("maestarr")


SCRIPT = _console_script()

pytestmark = pytest.mark.skipif(
    SCRIPT is None,
    reason="console script not installed — run `pip install -e \".[dev]\"` first",
)


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    assert SCRIPT is not None  # guarded by pytestmark
    return subprocess.run(
        [SCRIPT, *args],
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_console_script_prints_greeting():
    result = _run("hello")
    assert result.returncode == 0, result.stderr
    assert "Hello, world!" in result.stdout


def test_console_script_reports_version():
    # --version must work with no .env and no database — it is the smoke test
    # an operator reaches for when everything else is broken.
    result = _run("--version")
    assert result.returncode == 0, result.stderr
    assert __version__ in result.stdout
