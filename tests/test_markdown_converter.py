"""Unit tests for MarkdownConverter and OneNote tag transformations."""

from onebridge.core.markdown_converter import MarkdownConverter


def test_markdown_converter_basic():
    converter = MarkdownConverter()
    html = """
    <!DOCTYPE html>
    <html>
    <head><title>Planejamento Semanal</title></head>
    <body>
        <h1>Objetivos da Semana</h1>
        <p>Esta é uma nota de teste com <strong>negrito</strong> e <em>itálico</em>.</p>
        <ul>
            <li>Item 1</li>
            <li>Item 2</li>
        </ul>
    </body>
    </html>
    """
    metadata = {
        "title": "Planejamento Semanal",
        "id": "page-123",
        "notebook": "Caderno Pessoal",
        "section": "Metas",
        "created_at": "2024-01-01T10:00:00Z",
    }
    result = converter.convert(html, metadata=metadata)

    assert 'title: "Planejamento Semanal"' in result
    assert 'id: "page-123"' in result
    assert 'notebook: "Caderno Pessoal"' in result
    assert 'section: "Metas"' in result
    assert "# Objetivos da Semana" in result
    assert "**negrito**" in result
    assert "*itálico*" in result
    assert "- Item 1" in result or "* Item 1" in result


def test_markdown_converter_todo_checkboxes():
    converter = MarkdownConverter()
    html = """
    <body>
        <p data-tag="to-do">Comprar café</p>
        <p data-tag="to-do:completed">Enviar relatório semanal</p>
        <p>Item normal</p>
    </body>
    """
    result = converter.convert(html, metadata={"title": "Checklist"})
    assert "- [ ] Comprar café" in result
    assert "- [x] Enviar relatório semanal" in result
    assert "Item normal" in result


def test_markdown_converter_table():
    converter = MarkdownConverter()
    html = """
    <body>
        <table>
            <tr><th>Item</th><th>Quantidade</th><th>Preço</th></tr>
            <tr><td>Teclado</td><td>1</td><td>R$ 150</td></tr>
            <tr><td>Mouse</td><td>2</td><td>R$ 80</td></tr>
        </table>
    </body>
    """
    result = converter.convert(html, metadata={"title": "Tabela"})
    assert "| Item | Quantidade | Preço |" in result
    assert "| --- | --- | --- |" in result
    assert "| Teclado | 1 | R$ 150 |" in result
    assert "| Mouse | 2 | R$ 80 |" in result


def test_markdown_converter_assets_replacement():
    converter = MarkdownConverter()
    html = """
    <body>
        <p>Veja a imagem abaixo:</p>
        <img src="https://graph.microsoft.com/v1.0/resources/img1/$value" alt="Diagrama de Arquitetura" />
        <p>E baixe a planilha:</p>
        <object data="https://graph.microsoft.com/v1.0/resources/file1/$value" data-attachment="orcamento.xlsx" type="application/vnd.ms-excel"></object>
    </body>
    """
    image_map = {
        "https://graph.microsoft.com/v1.0/resources/img1/$value": "IMAGENS/diagrama_arquitetura.png"
    }
    attachment_map = {
        "https://graph.microsoft.com/v1.0/resources/file1/$value": "ANEXOS/orcamento.xlsx",
        "orcamento.xlsx": "ANEXOS/orcamento.xlsx",
    }

    result = converter.convert(
        html,
        metadata={"title": "Nota com Assets"},
        image_map=image_map,
        attachment_map=attachment_map,
    )

    assert "![Diagrama de Arquitetura](IMAGENS/diagrama_arquitetura.png)" in result
    assert "[📎 orcamento.xlsx](ANEXOS/orcamento.xlsx)" in result
