"""Unit tests for OneBridge CLI list-sections commands."""

import json
from unittest.mock import MagicMock, patch
from click.testing import CliRunner

from onebridge.api.dto import NotebookDTO, NotebookTreeDTO, SectionDTO, SectionGroupDTO
from onebridge.cli.main import cli


def test_cli_list_sections_table(tmp_path):
    db_file = tmp_path / "auth.db"
    runner = CliRunner()

    mock_sections = [
        SectionDTO(
            id="sec-1",
            name="Anotações Gerais",
            parent_path="Projetos / 2024",
            modified_at="2023-11-01T10:00:00Z",
            is_default=True,
        ),
        SectionDTO(
            id="sec-2",
            name="Ideias",
            parent_path="",
            modified_at="2023-10-15T09:00:00Z",
            is_default=False,
        ),
    ]

    with patch("onebridge.api.client.OneBridgeAPI.list_sections", return_value=mock_sections):
        result = runner.invoke(cli, ["list-sections", "Meu Caderno", "--db-path", str(db_file)])
        assert result.exit_code == 0
        assert "Anotações Gerais" in result.output
        assert "Projetos / 2024" in result.output
        assert "Ideias" in result.output
        assert "Total de seções: 2" in result.output


def test_cli_list_sections_tree(tmp_path):
    db_file = tmp_path / "auth.db"
    runner = CliRunner()

    mock_tree = NotebookTreeDTO(
        notebook=NotebookDTO(id="nb-123", name="Caderno Pessoal"),
        sections=[SectionDTO(id="sec-root", name="Seção Raiz", is_default=True)],
        section_groups=[
            SectionGroupDTO(
                id="sg-1",
                name="Trabalho",
                sections=[SectionDTO(id="sec-work", name="Tarefas Semanais")],
                section_groups=[
                    SectionGroupDTO(
                        id="sg-sub",
                        name="Arquivados",
                        sections=[SectionDTO(id="sec-arch", name="2023 Notas")],
                    )
                ],
            )
        ],
    )

    with patch("onebridge.api.client.OneBridgeAPI.get_notebook_tree", return_value=mock_tree):
        result = runner.invoke(cli, ["list-sections", "nb-123", "--tree", "--db-path", str(db_file)])
        assert result.exit_code == 0
        assert "Caderno Pessoal" in result.output
        assert "Seção Raiz" in result.output
        assert "Trabalho" in result.output
        assert "Tarefas Semanais" in result.output
        assert "Arquivados" in result.output
        assert "2023 Notas" in result.output
        assert "Total de seções na hierarquia: 3" in result.output


def test_cli_list_sections_json(tmp_path):
    db_file = tmp_path / "auth.db"
    runner = CliRunner()

    mock_sections = [
        SectionDTO(id="sec-json", name="Seção JSON", parent_path="Grupo A")
    ]

    with patch("onebridge.api.client.OneBridgeAPI.list_sections", return_value=mock_sections):
        result = runner.invoke(cli, ["list-sections", "nb-json", "--json", "--db-path", str(db_file)])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert len(parsed) == 1
        assert parsed[0]["name"] == "Seção JSON"
        assert parsed[0]["parent_path"] == "Grupo A"


def test_cli_list_sections_tree_json(tmp_path):
    db_file = tmp_path / "auth.db"
    runner = CliRunner()

    mock_tree = NotebookTreeDTO(
        notebook=NotebookDTO(id="nb-json", name="Caderno Tree JSON"),
        sections=[],
        section_groups=[],
    )

    with patch("onebridge.api.client.OneBridgeAPI.get_notebook_tree", return_value=mock_tree):
        result = runner.invoke(cli, ["list-sections", "nb-json", "--format", "tree", "--json", "--db-path", str(db_file)])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["notebook"]["name"] == "Caderno Tree JSON"


def test_cli_list_sections_csv(tmp_path):
    db_file = tmp_path / "auth.db"
    runner = CliRunner()

    mock_sections = [
        SectionDTO(id="sec-csv", name="Seção CSV", parent_path="Grupo CSV")
    ]

    with patch("onebridge.api.client.OneBridgeAPI.list_sections", return_value=mock_sections):
        result = runner.invoke(cli, ["list-sections", "nb-csv", "--format", "csv", "--db-path", str(db_file)])
        assert result.exit_code == 0
        assert "id,name,parent_path,created_at" in result.output
        assert "sec-csv,Seção CSV,Grupo CSV" in result.output


def test_cli_list_sections_aliases(tmp_path):
    db_file = tmp_path / "auth.db"
    runner = CliRunner()

    mock_sections = [SectionDTO(id="sec-a", name="Sec A")]

    with patch("onebridge.api.client.OneBridgeAPI.list_sections", return_value=mock_sections):
        res1 = runner.invoke(cli, ["list_sections", "nb-alias", "--db-path", str(db_file)])
        assert res1.exit_code == 0
        assert "Sec A" in res1.output

        res2 = runner.invoke(cli, ["sections", "nb-alias", "--db-path", str(db_file)])
        assert res2.exit_code == 0
        assert "Sec A" in res2.output
