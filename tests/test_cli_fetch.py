"""Unit tests for OneBridge CLI fetch-page and fetch-pages commands."""

import json
from unittest.mock import MagicMock, patch
from click.testing import CliRunner
from onebridge.api.dto import BatchExportResultDTO, PageExportResultDTO
from onebridge.cli.main import cli


def test_cli_fetch_page_success(tmp_path):
    runner = CliRunner()
    db_file = tmp_path / "auth.db"

    mock_result = PageExportResultDTO(
        page_id="pg-123",
        title="Planejamento Trimestral",
        file_path=str(tmp_path / "ARQUIVOS" / "Trabalho" / "Geral" / "Planejamento Trimestral.md"),
        relative_path="ARQUIVOS/Trabalho/Geral/Planejamento Trimestral.md",
        notebook_name="Trabalho",
        section_name="Geral",
        images_downloaded=2,
        attachments_downloaded=1,
        file_size_bytes=1024,
        success=True,
    )

    with patch("onebridge.api.client.OneBridgeAPI.fetch_page", return_value=mock_result):
        res = runner.invoke(
            cli,
            ["fetch-page", "Planejamento Trimestral", "--db-path", str(db_file)],
        )
        assert res.exit_code == 0
        assert "Página exportada com sucesso em formato Markdown!" in res.output
        assert "Planejamento Trimestral" in res.output
        assert "pg-123" in res.output
        assert "Trabalho" in res.output
        assert "2 salva(s)" in res.output
        assert "1 salvo(s)" in res.output


def test_cli_fetch_page_json(tmp_path):
    runner = CliRunner()
    db_file = tmp_path / "auth.db"

    mock_result = PageExportResultDTO(
        page_id="pg-json",
        title="Nota JSON",
        file_path=str(tmp_path / "Nota JSON.md"),
        relative_path="ARQUIVOS/Nota JSON.md",
        notebook_name="NB",
        section_name="SEC",
        images_downloaded=0,
        attachments_downloaded=0,
        file_size_bytes=500,
        success=True,
    )

    with patch("onebridge.api.client.OneBridgeAPI.fetch_page", return_value=mock_result):
        res = runner.invoke(
            cli,
            ["fetch-page", "Nota JSON", "--json", "--db-path", str(db_file)],
        )
        assert res.exit_code == 0
        data = json.loads(res.output)
        assert data["page_id"] == "pg-json"
        assert data["title"] == "Nota JSON"
        assert data["success"] is True


def test_cli_fetch_pages_success(tmp_path):
    runner = CliRunner()
    db_file = tmp_path / "auth.db"

    page_res = PageExportResultDTO(
        page_id="p1",
        title="Nota 1",
        file_path=str(tmp_path / "Nota 1.md"),
        relative_path="ARQUIVOS/NB/SEC/Nota 1.md",
        notebook_name="NB",
        section_name="SEC",
        images_downloaded=1,
        attachments_downloaded=0,
        file_size_bytes=800,
        success=True,
    )
    mock_batch = BatchExportResultDTO(
        total_pages=1,
        successful_pages=1,
        failed_pages=0,
        total_images=1,
        total_attachments=0,
        output_directory=str(tmp_path / "ARQUIVOS"),
        results=[page_res],
        elapsed_seconds=0.5,
    )

    with patch("onebridge.api.client.OneBridgeAPI.fetch_pages", return_value=mock_batch):
        res = runner.invoke(
            cli,
            ["fetch-pages", "--notebook", "NB", "--db-path", str(db_file)],
        )
        assert res.exit_code == 0
        assert "Exportação em lote concluída com sucesso!" in res.output
        assert "1 de 1" in res.output
        assert "Total de imagens:" in res.output


def test_cli_fetch_page_aliases(tmp_path):
    runner = CliRunner()
    db_file = tmp_path / "auth.db"

    mock_result = PageExportResultDTO(
        page_id="p-alias",
        title="Nota Alias",
        file_path="ARQUIVOS/Nota Alias.md",
        relative_path="ARQUIVOS/Nota Alias.md",
        notebook_name="NB",
        section_name="SEC",
        images_downloaded=0,
        attachments_downloaded=0,
        file_size_bytes=100,
        success=True,
    )

    with patch("onebridge.api.client.OneBridgeAPI.fetch_page", return_value=mock_result):
        res = runner.invoke(cli, ["fetch_page", "Nota Alias", "--db-path", str(db_file)])
        assert res.exit_code == 0
        assert "Nota Alias" in res.output


def test_cli_fetch_page_with_delay_ms(tmp_path):
    runner = CliRunner()
    db_file = tmp_path / "auth.db"

    mock_result = PageExportResultDTO(
        page_id="p-delay",
        title="Nota Delay",
        file_path="ARQUIVOS/Nota Delay.md",
        relative_path="ARQUIVOS/Nota Delay.md",
        notebook_name="NB",
        section_name="SEC",
        images_downloaded=0,
        attachments_downloaded=0,
        file_size_bytes=100,
        success=True,
    )

    with patch("onebridge.api.client.OneBridgeAPI.fetch_page", return_value=mock_result) as mock_fetch:
        res = runner.invoke(
            cli,
            ["fetch-page", "Nota Delay", "--delay-ms", "500", "--db-path", str(db_file)],
        )
        assert res.exit_code == 0
        mock_fetch.assert_called_once()
        assert mock_fetch.call_args[1]["delay_ms"] == 500


def test_cli_fetch_pages_with_delay_ms(tmp_path):
    runner = CliRunner()
    db_file = tmp_path / "auth.db"

    mock_batch = BatchExportResultDTO(
        total_pages=0,
        successful_pages=0,
        failed_pages=0,
        total_images=0,
        total_attachments=0,
        output_directory=str(tmp_path / "ARQUIVOS"),
        results=[],
        elapsed_seconds=0.1,
    )

    with patch("onebridge.api.client.OneBridgeAPI.fetch_pages", return_value=mock_batch) as mock_fetch:
        res = runner.invoke(
            cli,
            ["fetch-pages", "--notebook", "NB", "--delay-ms", "600", "--db-path", str(db_file)],
        )
        assert res.exit_code == 0
        mock_fetch.assert_called_once()
        assert mock_fetch.call_args[1]["delay_ms"] == 600
