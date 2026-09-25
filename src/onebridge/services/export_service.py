"""ExportService orchestrates fetching, converting, and saving OneNote pages as Markdown."""

import time
from pathlib import Path
from typing import Callable, List, Optional, Union

from onebridge.api.dto import (
    BatchExportResultDTO,
    PageDTO,
    PageExportResultDTO,
    SectionDTO,
)
from onebridge.config import DEFAULT_EXPORT_DIR
from onebridge.core.asset_pipeline import AssetPipeline
from onebridge.core.filesystem_writer import FileSystemWriter
from onebridge.core.graph_client import GraphAPIError, OneNoteGraphClient
from onebridge.core.markdown_converter import MarkdownConverter
from onebridge.logger import get_logger
from onebridge.services.catalog_service import CatalogService

logger = get_logger("onebridge.services.export_service")


class ExportService:
    """Orchestrates page export operations to local Markdown files."""

    def __init__(
        self,
        catalog_service: Optional[CatalogService] = None,
        graph_client: Optional[OneNoteGraphClient] = None,
        markdown_converter: Optional[MarkdownConverter] = None,
        asset_pipeline: Optional[AssetPipeline] = None,
        filesystem_writer: Optional[FileSystemWriter] = None,
    ):
        self.graph_client = graph_client or OneNoteGraphClient()
        self.catalog_service = catalog_service or CatalogService(graph_client=self.graph_client)
        self.converter = markdown_converter or MarkdownConverter()
        self.fs_writer = filesystem_writer or FileSystemWriter()
        self.asset_pipeline = asset_pipeline or AssetPipeline(
            graph_client=self.graph_client,
            fs_writer=self.fs_writer,
        )

    def _export_single_page_dto(
        self,
        page: PageDTO,
        token: str,
        output_dir: Optional[Union[str, Path]] = None,
        overwrite: bool = True,
        known_notebook_name: Optional[str] = None,
        known_section_name: Optional[str] = None,
        known_parent_path: Optional[str] = None,
    ) -> PageExportResultDTO:
        """Helper to export a resolved PageDTO."""
        fs_writer = FileSystemWriter(base_output_dir=output_dir)
        pipeline = AssetPipeline(graph_client=self.graph_client, fs_writer=fs_writer)

        try:
            # 1. Resolve hierarchy if not provided
            if known_notebook_name and known_section_name:
                nb_name = known_notebook_name
                sec_name = known_section_name
                parent_path = known_parent_path
            else:
                nb, sec, parent_path = self.catalog_service.get_page_hierarchy(page, token=token)
                nb_name = nb.name
                sec_name = sec.name

            section_dir = fs_writer.resolve_section_dir(
                notebook_name=nb_name,
                section_name=sec_name,
                parent_path=parent_path,
            )

            # 2. Fetch raw HTML
            html_content = self.graph_client.get_page_content(page_id=page.id, token=token)

            # 3. Process and download assets (IMAGENS/ and ANEXOS/)
            img_map, att_map, imgs, atts = pipeline.process_assets(
                html_content=html_content,
                section_dir=section_dir,
                token=token,
                page_title=page.title,
            )

            # 4. Prepare metadata and convert to Markdown
            metadata = {
                "title": page.title,
                "id": page.id,
                "notebook": nb_name,
                "section": sec_name,
                "section_group": parent_path,
                "created_at": page.created_at,
                "modified_at": page.modified_at,
                "web_url": page.web_url,
            }

            md_content = self.converter.convert(
                html_content=html_content,
                metadata=metadata,
                image_map=img_map,
                attachment_map=att_map,
            )

            # 5. Write Markdown file
            md_path = fs_writer.write_markdown_page(
                section_dir=section_dir,
                title=page.title,
                markdown_content=md_content,
                overwrite=overwrite,
            )

            file_size = md_path.stat().st_size if md_path.exists() else 0
            rel_path = str(md_path)
            try:
                rel_path = str(md_path.relative_to(Path.cwd()))
            except ValueError:
                pass

            logger.info(f"Página exportada com sucesso: '{page.title}' -> {rel_path} ({len(imgs)} imgs, {len(atts)} anexos)")

            return PageExportResultDTO(
                page_id=page.id,
                title=page.title,
                file_path=str(md_path.resolve()),
                relative_path=rel_path,
                notebook_name=nb_name,
                section_name=sec_name,
                section_group=parent_path,
                images_downloaded=len(imgs),
                attachments_downloaded=len(atts),
                file_size_bytes=file_size,
                success=True,
                error_message=None,
            )

        except Exception as e:
            logger.error(f"Falha ao exportar página '{page.title}': {e}", exc_info=True)
            return PageExportResultDTO(
                page_id=page.id,
                title=page.title,
                file_path="",
                relative_path="",
                notebook_name=known_notebook_name or "Desconhecido",
                section_name=known_section_name or "Desconhecido",
                section_group=known_parent_path,
                images_downloaded=0,
                attachments_downloaded=0,
                file_size_bytes=0,
                success=False,
                error_message=str(e),
            )

    def export_page(
        self,
        page_id_or_title: str,
        token: str,
        section: Optional[str] = None,
        notebook: Optional[str] = None,
        output_dir: Optional[Union[str, Path]] = None,
        overwrite: bool = True,
        delay_ms: Optional[int] = None,
    ) -> PageExportResultDTO:
        """Exports a single page by title or ID to a local Markdown file."""
        logger.info(f"Iniciando exportação da página: '{page_id_or_title}'")
        if delay_ms is not None:
            self.graph_client.set_request_delay_ms(delay_ms)

        page = self.catalog_service.resolve_page(
            page_id_or_title=page_id_or_title,
            token=token,
            section_id_or_name=section,
            notebook_id_or_name=notebook,
        )

        result = self._export_single_page_dto(
            page=page,
            token=token,
            output_dir=output_dir,
            overwrite=overwrite,
        )

        if not result.success:
            logger.error(f"Erro ao exportar página '{page.title}': {result.error_message}")
            raise RuntimeError(f"Erro ao exportar página '{page.title}': {result.error_message}")

        return result

    def export_pages(
        self,
        token: str,
        notebook: Optional[str] = None,
        section: Optional[str] = None,
        recursive: bool = True,
        output_dir: Optional[Union[str, Path]] = None,
        overwrite: bool = True,
        delay_ms: Optional[int] = None,
        on_progress: Optional[Callable[[PageExportResultDTO, int, int], None]] = None,
    ) -> BatchExportResultDTO:
        """Batch exports multiple pages from a section or an entire notebook hierarchy."""
        if delay_ms is not None:
            self.graph_client.set_request_delay_ms(delay_ms)

        start_time = time.time()
        target_dir = Path(output_dir or DEFAULT_EXPORT_DIR)

        pages_to_export: List[tuple[PageDTO, str, str, Optional[str]]] = []

        if section:
            # Export all pages from a specific section
            sec_dto = self.catalog_service.resolve_section(
                section_id_or_name=section,
                token=token,
                notebook_id_or_name=notebook,
            )
            nb_name = notebook
            if not nb_name and sec_dto.parent_notebook_id:
                try:
                    nb_dto = self.catalog_service.get_notebook(sec_dto.parent_notebook_id, token=token)
                    nb_name = nb_dto.name
                except Exception:
                    nb_name = "OneNote"
            elif not nb_name:
                nb_name = "OneNote"

            pages = self.catalog_service.list_pages(
                section_id_or_name=sec_dto.id,
                token=token,
            )
            for p in pages:
                pages_to_export.append((p, nb_name, sec_dto.name, sec_dto.parent_path))

        elif notebook:
            # Export all sections from a notebook
            nb_dto = self.catalog_service.resolve_notebook(notebook_id_or_name=notebook, token=token)
            sections = self.catalog_service.list_sections(
                notebook_id_or_name=nb_dto.id,
                token=token,
                recursive=recursive,
            )
            for s in sections:
                pages = self.catalog_service.list_pages(
                    section_id_or_name=s.id,
                    token=token,
                )
                for p in pages:
                    pages_to_export.append((p, nb_dto.name, s.name, s.parent_path))

        else:
            raise ValueError(
                "Informe um caderno (--notebook) ou uma seção (--section) para exportar as páginas."
            )

        results: List[PageExportResultDTO] = []
        total = len(pages_to_export)
        total_imgs = 0
        total_atts = 0
        successful = 0
        failed = 0

        for idx, (page, nb_name, sec_name, parent_path) in enumerate(pages_to_export, start=1):
            res = self._export_single_page_dto(
                page=page,
                token=token,
                output_dir=target_dir,
                overwrite=overwrite,
                known_notebook_name=nb_name,
                known_section_name=sec_name,
                known_parent_path=parent_path,
            )
            results.append(res)
            if res.success:
                successful += 1
                total_imgs += res.images_downloaded
                total_atts += res.attachments_downloaded
            else:
                failed += 1

            if on_progress:
                on_progress(res, idx, total)

        elapsed = time.time() - start_time

        return BatchExportResultDTO(
            total_pages=total,
            successful_pages=successful,
            failed_pages=failed,
            total_images=total_imgs,
            total_attachments=total_atts,
            output_directory=str(target_dir.resolve()),
            results=results,
            elapsed_seconds=round(elapsed, 2),
        )
