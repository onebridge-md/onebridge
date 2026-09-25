"""Unit tests for AssetPipeline."""

from pathlib import Path
from unittest.mock import MagicMock
from onebridge.core.asset_pipeline import AssetPipeline
from onebridge.core.filesystem_writer import FileSystemWriter


def test_asset_pipeline_images_and_attachments(tmp_path):
    mock_graph = MagicMock()
    # Mock binary return values for images and attachments
    fake_png = b"\x89PNG\r\n\x1a\nfake_image_data"
    fake_pdf = b"%PDF-1.4 fake_pdf_data"

    def mock_get_binary(url, token):
        if "img1" in url:
            return fake_png
        return fake_pdf

    mock_graph.get_binary_resource.side_effect = mock_get_binary

    fs_writer = FileSystemWriter(base_output_dir=tmp_path)
    pipeline = AssetPipeline(graph_client=mock_graph, fs_writer=fs_writer)

    html = """
    <body>
        <p>Imagem:</p>
        <img src="https://graph.microsoft.com/v1.0/resources/img1/$value" alt="grafico" />
        <p>Anexo:</p>
        <object data="https://graph.microsoft.com/v1.0/resources/pdf1/$value" data-attachment="relatorio.pdf"></object>
    </body>
    """

    sec_dir = fs_writer.resolve_section_dir("NB", "SEC")
    img_map, att_map, imgs, atts = pipeline.process_assets(
        html_content=html,
        section_dir=sec_dir,
        token="test-token",
        page_title="Minha Nota",
    )

    assert len(imgs) == 1
    assert "IMAGENS/grafico.png" in img_map.values()
    saved_img = sec_dir / "IMAGENS" / "grafico.png"
    assert saved_img.exists()
    assert saved_img.read_bytes() == fake_png

    assert len(atts) == 1
    assert "ANEXOS/relatorio.pdf" in att_map.values()
    saved_att = sec_dir / "ANEXOS" / "relatorio.pdf"
    assert saved_att.exists()
    assert saved_att.read_bytes() == fake_pdf
