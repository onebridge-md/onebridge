"""Unit tests for OneBridge CLI commands."""

from unittest.mock import MagicMock, patch
from click.testing import CliRunner

from onebridge.cli.main import cli


def test_cli_help():
    """Test CLI help output."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "login" in result.output
    assert "status" in result.output
    assert "logout" in result.output
    assert "tui" in result.output


def test_cli_status_unauthenticated(tmp_path):
    """Test status command when no token is cached."""
    db_file = tmp_path / "auth.db"
    runner = CliRunner()
    result = runner.invoke(cli, ["status", "--db-path", str(db_file)])
    assert result.exit_code != 0
    assert "Nenhuma conta autenticada" in result.output


def test_cli_logout(tmp_path):
    """Test logout command."""
    db_file = tmp_path / "auth.db"
    runner = CliRunner()
    result = runner.invoke(cli, ["logout", "--db-path", str(db_file)])
    assert result.exit_code == 0
    assert "Sessão encerrada" in result.output
