"""Unit tests for OneBridge CLI list-notebooks commands."""

import json
from unittest.mock import MagicMock, patch
from click.testing import CliRunner

from onebridge.api.dto import NotebookDTO
from onebridge.cli.main import cli


def test_cli_list_notebooks_unauthenticated(tmp_path):
    db_file = tmp_path / "auth.db"
    runner = CliRunner()
    result = runner.invoke(cli, ["list-notebooks", "--db-path", str(db_file)])
    assert result.exit_code != 0
    assert "Nenhuma sessão ativa" in result.output or "onebridge login" in result.output


def test_cli_list_notebooks_success(tmp_path):
    db_file = tmp_path / "auth.db"
    runner = CliRunner()

    mock_notebooks = [
        NotebookDTO(
            id="nb-001",
            name="Caderno de Projetos",
            modified_at="2023-10-15T14:30:00Z",
            is_default=True,
            user_role="Owner",
            web_url="https://onenote.com/nb001",
        ),
        NotebookDTO(
            id="nb-002",
            name="Anotações Gerais",
            modified_at="2023-09-10T11:00:00Z",
            is_default=False,
            user_role="Owner",
            web_url="https://onenote.com/nb002",
        ),
    ]

    with patch("onebridge.api.client.OneBridgeAPI.list_notebooks", return_value=mock_notebooks):
        result = runner.invoke(cli, ["list-notebooks", "--db-path", str(db_file)])
        assert result.exit_code == 0
        assert "Caderno de Projetos" in result.output
        assert "Anotações Gerais" in result.output
        assert "Total de cadernos: 2" in result.output


def test_cli_list_notebooks_json_output(tmp_path):
    db_file = tmp_path / "auth.db"
    runner = CliRunner()

    mock_notebooks = [
        NotebookDTO(
            id="nb-001",
            name="Caderno JSON",
            modified_at="2023-10-15T14:30:00Z",
            is_default=True,
            user_role="Owner",
        )
    ]

    with patch("onebridge.api.client.OneBridgeAPI.list_notebooks", return_value=mock_notebooks):
        result = runner.invoke(cli, ["list-notebooks", "--json", "--db-path", str(db_file)])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert len(parsed) == 1
        assert parsed[0]["name"] == "Caderno JSON"
        assert parsed[0]["id"] == "nb-001"


def test_cli_list_notebooks_csv_output(tmp_path):
    db_file = tmp_path / "auth.db"
    runner = CliRunner()

    mock_notebooks = [
        NotebookDTO(
            id="nb-001",
            name="Caderno CSV",
            modified_at="2023-10-15T14:30:00Z",
            is_default=True,
            user_role="Owner",
        )
    ]

    with patch("onebridge.api.client.OneBridgeAPI.list_notebooks", return_value=mock_notebooks):
        result = runner.invoke(cli, ["list-notebooks", "--format", "csv", "--db-path", str(db_file)])
        assert result.exit_code == 0
        assert "id,name,created_at,modified_at" in result.output
        assert "nb-001,Caderno CSV" in result.output


def test_cli_list_notebooks_aliases(tmp_path):
    db_file = tmp_path / "auth.db"
    runner = CliRunner()

    mock_notebooks = [NotebookDTO(id="nb-alias", name="Alias Test")]

    with patch("onebridge.api.client.OneBridgeAPI.list_notebooks", return_value=mock_notebooks):
        res1 = runner.invoke(cli, ["list_notebooks", "--db-path", str(db_file)])
        assert res1.exit_code == 0
        assert "Alias Test" in res1.output

        res2 = runner.invoke(cli, ["notebooks", "--db-path", str(db_file)])
        assert res2.exit_code == 0
        assert "Alias Test" in res2.output
