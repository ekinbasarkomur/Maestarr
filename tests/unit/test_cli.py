from typer.testing import CliRunner

from maestarr import __version__
from maestarr.cli import app

runner = CliRunner()


def test_hello_prints_greeting():
    result = runner.invoke(app, ["hello"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "Hello, world!"


def test_version_reports_version_and_specs():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout
    assert "specs applied:" in result.stdout


def test_no_args_shows_help():
    # no_args_is_help=True routes through Click's usage error path, which exits 2.
    result = runner.invoke(app, [])
    assert result.exit_code == 2
    assert "hello" in result.stdout
