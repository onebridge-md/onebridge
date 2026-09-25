"""Unit tests for OneBridge CLI list-pages, set-notebook, and set-section commands."""

import json
from unittest.mock import MagicMock, patch
from click.testing import CliRunner

from onebridge.api.dto import NotebookDTO, PageDTO, SectionDTO
from onebridge.cli.main import cli


def test_cli_set_and_show_notebook(tmp_path):
    db_file = tmp_path / "auth.db"
    runner = CliRunner()

    mock_nb = NotebookDTO(id="nb-100", name="Caderno de Trabalho")

    with patch("onebridge.auth.client.OneNoteAuthenticator.get_valid_token", return_value="fake-token"), \
         patch("onebridge.services.catalog_service.CatalogService.resolve_notebook", return_value=mock_nb):
        # Set notebook
        res = runner.invoke(cli, ["set-notebook", "Caderno de Trabalho", "--db-path", str(db_file)])
        assert res.exit_code == 0
        assert "Caderno padrão configurado com sucesso!" in res.output
        assert "Caderno de Trabalho" in res.output
        assert "nb-100" in res.output

    # Show notebook
    res_show = runner.invoke(cli, ["set-notebook", "--show", "--db-path", str(db_file)])
    assert res_show.exit_code == 0
    assert "Caderno padrão atual:" in res_show.output
    assert "Caderno de Trabalho" in res_show.output

    # Clear notebook
    res_clear = runner.invoke(cli, ["set-notebook", "--clear", "--db-path", str(db_file)])
    assert res_clear.exit_code == 0
    assert "removida com sucesso" in res_clear.output

    # Show when empty
    res_empty = runner.invoke(cli, ["set-notebook", "--show", "--db-path", str(db_file)])
    assert res_empty.exit_code == 0
    assert "Nenhum caderno padrão configurado" in res_empty.output


def test_cli_set_and_show_section(tmp_path):
    db_file = tmp_path / "auth.db"
    runner = CliRunner()

    mock_sec = SectionDTO(id="sec-200", name="Anotações Rápidas", parent_notebook_id="nb-100")

    with patch("onebridge.auth.client.OneNoteAuthenticator.get_valid_token", return_value="fake-token"), \
         patch("onebridge.services.catalog_service.CatalogService.resolve_section", return_value=mock_sec):
        # Set section
        res = runner.invoke(cli, ["set-section", "Anotações Rápidas", "--db-path", str(db_file)])
        assert res.exit_code == 0
        assert "Seção padrão configurada com sucesso!" in res.output
        assert "Anotações Rápidas" in res.output
        assert "sec-200" in res.output

    # Show section
    res_show = runner.invoke(cli, ["set-section", "--show", "--db-path", str(db_file)])
    assert res_show.exit_code == 0
    assert "Seção padrão atual:" in res_show.output
    assert "Anotações Rápidas" in res_show.output

    # Clear section
    res_clear = runner.invoke(cli, ["set-section", "--clear", "--db-path", str(db_file)])
    assert res_clear.exit_code == 0
    assert "removida com sucesso" in res_clear.output


def test_cli_list_pages_table(tmp_path):
    db_file = tmp_path / "auth.db"
    runner = CliRunner()

    mock_pages = [
        PageDTO(
            id="pg-1",
            title="Planejamento Anual",
            level=0,
            order=1,
            created_at="2024-01-01T10:00:00Z",
            modified_at="2024-01-05T15:30:00Z",
            parent_section_name="Projetos",
        ),
        PageDTO(
            id="pg-2",
            title="Q1 Metas",
            level=1,
            order=2,
            created_at="2024-01-02T11:00:00Z",
            modified_at="2024-01-06T16:00:00Z",
            parent_section_name="Projetos",
        ),
    ]

    with patch("onebridge.api.client.OneBridgeAPI.list_pages", return_value=mock_pages):
        result = runner.invoke(
            cli,
            ["list-pages", "Projetos", "--notebook", "Empresa", "--db-path", str(db_file)],
        )
        assert result.exit_code == 0
        assert "Caderno: Empresa" in result.output
        assert "Seção:   Projetos" in result.output
        assert "Planejamento Anual" in result.output
        assert "↳ Q1 Metas" in result.output
        assert "Total de páginas: 2" in result.output


def test_cli_list_pages_json(tmp_path):
    db_file = tmp_path / "auth.db"
    runner = CliRunner()

    mock_pages = [
        PageDTO(
            id="pg-json",
            title="Página JSON",
            level=0,
            parent_section_name="Seção JSON",
        )
    ]

    with patch("onebridge.api.client.OneBridgeAPI.list_pages", return_value=mock_pages):
        result = runner.invoke(
            cli,
            ["list-pages", "Seção JSON", "--json", "--db-path", str(db_file)],
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert len(parsed) == 1
        assert parsed[0]["title"] == "Página JSON"
        assert parsed[0]["id"] == "pg-json"


def test_cli_list_pages_csv_and_plain(tmp_path):
    db_file = tmp_path / "auth.db"
    runner = CliRunner()

    mock_pages = [
        PageDTO(
            id="pg-csv",
            title="Página CSV",
            level=0,
            created_at="2024-01-01T00:00:00Z",
            modified_at="2024-01-02T00:00:00Z",
            parent_section_name="Seção CSV",
        )
    ]

    with patch("onebridge.api.client.OneBridgeAPI.list_pages", return_value=mock_pages):
        # CSV
        res_csv = runner.invoke(
            cli,
            ["list-pages", "Seção CSV", "--format", "csv", "--db-path", str(db_file)],
        )
        assert res_csv.exit_code == 0
        assert "id,title,level,order" in res_csv.output
        assert "pg-csv,Página CSV,0" in res_csv.output

        # Plain
        res_plain = runner.invoke(
            cli,
            ["list-pages", "Seção CSV", "--format", "plain", "--db-path", str(db_file)],
        )
        assert res_plain.exit_code == 0
        assert "pg-csv\tPágina CSV\t0" in res_plain.output


def test_cli_list_pages_missing_section_message(tmp_path):
    db_file = tmp_path / "auth.db"
    runner = CliRunner()

    result = runner.invoke(cli, ["list-pages", "--db-path", str(db_file)])
    assert result.exit_code == 1
    assert "Nenhuma seção informada e nenhuma seção padrão configurada" in result.output


def test_cli_list_pages_aliases(tmp_path):
    db_file = tmp_path / "auth.db"
    runner = CliRunner()

    mock_pages = [PageDTO(id="pg-alias", title="Nota Alias", level=0)]

    with patch("onebridge.api.client.OneBridgeAPI.list_pages", return_value=mock_pages):
        res1 = runner.invoke(cli, ["list_pages", "Sec", "--db-path", str(db_file)])
        assert res1.exit_code == 0
        assert "Nota Alias" in res1.output

        res2 = runner.invoke(cli, ["pages", "Sec", "--db-path", str(db_file)])
        assert res2.exit_code == 0
        assert "Nota Alias" in res2.output
