"""Unit tests for ExportService."""

from pathlib import Path
from unittest.mock import MagicMock
from onebridge.api.dto import NotebookDTO, PageDTO, SectionDTO
from onebridge.services.export_service import ExportService


def test_export_service_single_page(tmp_path):
    mock_catalog = MagicMock()
    mock_graph = MagicMock()

    mock_page = PageDTO(id="pg-1", title="Anotação de Teste", parent_section_id="sec-1")
    mock_sec = SectionDTO(id="sec-1", name="Geral", parent_notebook_id="nb-1")
    mock_nb = NotebookDTO(id="nb-1", name="Caderno Pessoal")

    mock_catalog.resolve_page.return_value = mock_page
    mock_catalog.get_page_hierarchy.return_value = (mock_nb, mock_sec, None)
    mock_graph.get_page_content.return_value = "<html><body><h1>Hello World</h1></body></html>"

    service = ExportService(catalog_service=mock_catalog, graph_client=mock_graph)
    result = service.export_page(
        page_id_or_title="Anotação de Teste",
        token="token",
        output_dir=tmp_path,
    )

    assert result.success is True
    assert result.title == "Anotação de Teste"
    assert result.notebook_name == "Caderno Pessoal"
    assert result.section_name == "Geral"

    saved_file = Path(result.file_path)
    assert saved_file.exists()
    content = saved_file.read_text(encoding="utf-8")
    assert 'title: "Anotação de Teste"' in content
    assert "# Hello World" in content


def test_export_service_batch_pages(tmp_path):
    mock_catalog = MagicMock()
    mock_graph = MagicMock()

    mock_sec = SectionDTO(id="sec-1", name="Geral", parent_notebook_id="nb-1")
    mock_nb = NotebookDTO(id="nb-1", name="Caderno Pessoal")
    pages = [
        PageDTO(id="p1", title="Nota 1", parent_section_id="sec-1"),
        PageDTO(id="p2", title="Nota 2", parent_section_id="sec-1"),
    ]

    mock_catalog.resolve_section.return_value = mock_sec
    mock_catalog.get_notebook.return_value = mock_nb
    mock_catalog.list_pages.return_value = pages
    mock_graph.get_page_content.return_value = "<html><body><p>Conteúdo</p></body></html>"

    service = ExportService(catalog_service=mock_catalog, graph_client=mock_graph)
    batch_res = service.export_pages(
        token="token",
        section="Geral",
        output_dir=tmp_path,
    )

    assert batch_res.total_pages == 2
    assert batch_res.successful_pages == 2
    assert batch_res.failed_pages == 0
    assert len(batch_res.results) == 2
