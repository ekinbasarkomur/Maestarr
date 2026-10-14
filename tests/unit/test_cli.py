from typer.testing import CliRunner

from maestarr import __version__
from maestarr.cli import app

runner = CliRunner()


def test_version_reports_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_no_args_lists_the_real_commands():
    result = runner.invoke(app, [])
    assert result.exit_code == 2
    for command in ("serve", "serve-mcp", "doctor", "judge", "recommend", "telegram"):
        assert command in result.stdout


def test_doctor_reports_unconfigured_services():
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "not configured" in result.stdout
    assert "anilist" in result.stdout
