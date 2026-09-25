"""Unit tests for filesystem utilities and FileSystemWriter."""

from pathlib import Path
from onebridge.core.filesystem_writer import FileSystemWriter
from onebridge.utils.filesystem import (
    ensure_directory,
    get_unique_path,
    sanitize_filename,
    sanitize_path_segment,
)


def test_sanitize_filename():
    assert sanitize_filename("Minha Nota: Versão 2.0?") == "Minha Nota_ Versão 2.0_"
    assert sanitize_filename("Arquivo/com\\barras*e|chars<>invalidos.pdf") == "Arquivo_com_barras_e_chars_invalidos.pdf"
    assert sanitize_filename("   ...Espaços e pontos...   ") == "Espaços e pontos"
    assert sanitize_filename("") == "sem_titulo"
    assert sanitize_filename("   ") == "sem_titulo"


def test_sanitize_filename_max_length():
    long_name = "a" * 250 + ".md"
    sanitized = sanitize_filename(long_name, max_length=50)
    assert len(sanitized) <= 50
    assert sanitized.endswith(".md")


def test_sanitize_path_segment():
    assert sanitize_path_segment("Caderno <Principal>") == "Caderno _Principal_"
    assert sanitize_path_segment("Grupo / Subgrupo") == "Grupo _ Subgrupo"


def test_ensure_directory(tmp_path):
    target = tmp_path / "nested" / "dir" / "test"
    assert not target.exists()
    created = ensure_directory(target)
    assert created.is_dir()
    assert target.exists()


def test_get_unique_path(tmp_path):
    f = tmp_path / "nota.md"
    f.write_text("orig")
    unique1 = get_unique_path(f)
    assert unique1.name == "nota_1.md"

    unique1.write_text("v1")
    unique2 = get_unique_path(f)
    assert unique2.name == "nota_2.md"


def test_filesystem_writer_structure(tmp_path):
    writer = FileSystemWriter(base_output_dir=tmp_path)
    sec_dir = writer.resolve_section_dir(
        notebook_name="Trabalho",
        section_name="Reuniões",
        parent_path="Projetos / 2024",
    )
    expected = tmp_path / "Trabalho" / "Projetos" / "2024" / "Reuniões"
    assert sec_dir == expected
    assert sec_dir.is_dir()

    imgs = writer.get_images_dir(sec_dir)
    assert imgs == expected / "IMAGENS"
    assert imgs.is_dir()

    atts = writer.get_attachments_dir(sec_dir)
    assert atts == expected / "ANEXOS"
    assert atts.is_dir()


def test_filesystem_writer_write_markdown(tmp_path):
    writer = FileSystemWriter(base_output_dir=tmp_path)
    sec_dir = writer.resolve_section_dir("NB", "SEC")

    md_path = writer.write_markdown_page(sec_dir, "Minha Nota", "# Conteúdo", overwrite=True)
    assert md_path.name == "Minha Nota.md"
    assert md_path.read_text(encoding="utf-8") == "# Conteúdo"

    # Write without overwrite
    md_path_2 = writer.write_markdown_page(sec_dir, "Minha Nota", "# Conteúdo 2", overwrite=False)
    assert md_path_2.name == "Minha Nota_1.md"
    assert md_path_2.read_text(encoding="utf-8") == "# Conteúdo 2"
