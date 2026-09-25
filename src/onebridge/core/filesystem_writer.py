"""FileSystemWriter manages directory structure creation, path resolution, and file persistence."""

from pathlib import Path
from typing import Optional, Tuple, Union

from onebridge.config import DEFAULT_EXPORT_DIR
from onebridge.utils.filesystem import (
    ensure_directory,
    get_unique_path,
    sanitize_filename,
    sanitize_path_segment,
)


class FileSystemWriter:
    """Handles hierarchical directory structure creation and writing files to disk."""

    def __init__(self, base_output_dir: Optional[Union[str, Path]] = None):
        self.base_output_dir = Path(base_output_dir or DEFAULT_EXPORT_DIR)

    def resolve_section_dir(
        self,
        notebook_name: str,
        section_name: str,
        parent_path: Optional[str] = None,
    ) -> Path:
        """Constructs the nested directory path for a section inside a notebook.
        
        Example:
            ARQUIVOS / "Meu Caderno" / "Projetos" / "2024" / "Planejamento"
        """
        segments = [sanitize_path_segment(notebook_name or "Caderno_Sem_Nome")]

        if parent_path:
            # parent_path can be e.g. "Grupo1 / Subgrupo2" or "Grupo1/Subgrupo2"
            raw_groups = [g.strip() for g in parent_path.replace("\\", "/").split("/") if g.strip()]
            for g in raw_groups:
                segments.append(sanitize_path_segment(g))

        segments.append(sanitize_path_segment(section_name or "Secao_Sem_Nome"))

        section_dir = self.base_output_dir.joinpath(*segments)
        ensure_directory(section_dir)
        return section_dir

    def get_images_dir(self, section_dir: Path) -> Path:
        """Returns and ensures the IMAGENS directory inside a section."""
        images_dir = section_dir / "IMAGENS"
        ensure_directory(images_dir)
        return images_dir

    def get_attachments_dir(self, section_dir: Path) -> Path:
        """Returns and ensures the ANEXOS directory inside a section."""
        attachments_dir = section_dir / "ANEXOS"
        ensure_directory(attachments_dir)
        return attachments_dir

    def write_markdown_page(
        self,
        section_dir: Path,
        title: str,
        markdown_content: str,
        overwrite: bool = True,
    ) -> Path:
        """Writes page Markdown content to disk.
        
        Args:
            section_dir: Section directory.
            title: Page title.
            markdown_content: Rendered Markdown string.
            overwrite: If True, overwrites existing file with same name.
            
        Returns:
            Path of the written markdown file.
        """
        ensure_directory(section_dir)
        safe_title = sanitize_filename(title or "Sem Titulo")
        file_path = section_dir / f"{safe_title}.md"

        if not overwrite and file_path.exists():
            file_path = get_unique_path(file_path)

        file_path.write_text(markdown_content, encoding="utf-8")
        return file_path

    def write_asset(
        self,
        target_dir: Path,
        filename: str,
        data: bytes,
        overwrite: bool = True,
    ) -> Tuple[Path, str]:
        """Writes binary data (image or attachment) to target directory.
        
        Returns:
            Tuple of (Path to written file, final filename used).
        """
        ensure_directory(target_dir)
        safe_name = sanitize_filename(filename or "arquivo.bin")
        file_path = target_dir / safe_name

        if not overwrite and file_path.exists():
            file_path = get_unique_path(file_path)

        file_path.write_bytes(data)
        return file_path, file_path.name
