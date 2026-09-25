"""Public API Facade for OneBridge."""

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from onebridge.api.dto import (
    BatchExportResultDTO,
    NotebookDTO,
    NotebookTreeDTO,
    PageDTO,
    PageExportResultDTO,
    SectionDTO,
    SectionGroupDTO,
    UserProfileDTO,
)
from onebridge.auth.client import OneNoteAuthenticator
from onebridge.config import DB_PATH
from onebridge.core.graph_client import OneNoteGraphClient
from onebridge.services.catalog_service import CatalogService
from onebridge.services.export_service import ExportService
from onebridge.services.settings_service import SettingsService


class OneBridgeAPI:
    """Unified API boundary for CLI, TUI, and external integrations."""

    def __init__(
        self,
        authenticator: Optional[OneNoteAuthenticator] = None,
        catalog_service: Optional[CatalogService] = None,
        settings_service: Optional[SettingsService] = None,
        export_service: Optional[ExportService] = None,
        client_id: Optional[str] = None,
        authority: Optional[str] = None,
        db_path: Path = DB_PATH,
        request_delay_ms: Optional[int] = None,
    ):
        self.auth = authenticator or OneNoteAuthenticator(
            client_id=client_id,
            authority=authority,
            db_path=db_path,
        )
        self.catalog_service = catalog_service or CatalogService()
        self.settings = settings_service or SettingsService(db_path=db_path)
        graph_client = getattr(self.catalog_service, "graph_client", None)
        if request_delay_ms is not None and graph_client and hasattr(graph_client, "set_request_delay_ms"):
            graph_client.set_request_delay_ms(request_delay_ms)
        self.export_service = export_service or ExportService(
            catalog_service=self.catalog_service,
            graph_client=graph_client,
        )

    @property
    def graph_client(self) -> OneNoteGraphClient:
        """Access underlying OneNoteGraphClient via catalog_service."""
        return self.catalog_service.graph_client

    def is_authenticated(self) -> bool:
        """Check if an active, valid authentication session exists."""
        return bool(self.auth.get_token_silently())

    def get_current_user_profile(self) -> UserProfileDTO:
        """Retrieve authenticated user's profile information."""
        profile_data = self.auth.get_current_user_profile()
        return UserProfileDTO.from_graph_dict(profile_data)

    def list_notebooks(
        self,
        sort_by: str = "modified",
        reverse: bool = True,
    ) -> List[NotebookDTO]:
        """Fetch all notebooks available for the current user.
        
        Raises:
            RuntimeError: If the user is not authenticated or token renewal fails.
            GraphAPIError: If a Microsoft Graph API error occurs.
        """
        token = self.auth.get_valid_token()
        return self.catalog_service.list_notebooks(token=token, sort_by=sort_by, reverse=reverse)

    def get_notebook(self, notebook_id: str) -> NotebookDTO:
        """Fetch details of a single notebook by ID.
        
        Raises:
            RuntimeError: If unauthenticated.
            GraphAPIError: If request fails.
        """
        token = self.auth.get_valid_token()
        return self.catalog_service.get_notebook(notebook_id=notebook_id, token=token)

    def list_sections(
        self,
        notebook: str,
        recursive: bool = True,
        sort_by: str = "name",
        reverse: bool = False,
    ) -> List[SectionDTO]:
        """Fetch sections of a notebook (resolving notebook by ID or name).
        
        Args:
            notebook: ID or name of the notebook.
            recursive: If True, includes sections inside nested section groups (subsections).
            sort_by: Field to sort by ('name', 'modified', 'created', 'path').
            reverse: Sort order.
        """
        token = self.auth.get_valid_token()
        return self.catalog_service.list_sections(
            notebook_id_or_name=notebook,
            token=token,
            recursive=recursive,
            sort_by=sort_by,
            reverse=reverse,
        )

    def get_notebook_tree(self, notebook: str) -> NotebookTreeDTO:
        """Fetch full hierarchical tree of a notebook and its sections/subsections."""
        token = self.auth.get_valid_token()
        return self.catalog_service.get_notebook_tree(notebook_id_or_name=notebook, token=token)

    def get_section(self, section_id: str) -> SectionDTO:
        """Fetch details of a specific section by ID."""
        token = self.auth.get_valid_token()
        return self.catalog_service.get_section(section_id=section_id, token=token)

    def list_section_group_sections(
        self, section_group_id: str, parent_path: str = ""
    ) -> List[SectionDTO]:
        """Fetch direct sections within a specific section group."""
        token = self.auth.get_valid_token()
        return self.catalog_service.list_section_group_sections(
            section_group_id=section_group_id, token=token, parent_path=parent_path
        )

    def list_section_group_section_groups(
        self, section_group_id: str, parent_path: str = ""
    ) -> List[SectionGroupDTO]:
        """Fetch direct nested section groups within a specific section group."""
        token = self.auth.get_valid_token()
        return self.catalog_service.list_section_group_section_groups(
            section_group_id=section_group_id, token=token, parent_path=parent_path
        )

    def list_sections_in_section_group(
        self, section_group_id: str, recursive: bool = True
    ) -> List[SectionDTO]:
        """Fetch all sections under a section group (including nested subgroups if recursive=True)."""
        token = self.auth.get_valid_token()
        return self.catalog_service.list_sections_in_section_group(
            section_group_id=section_group_id, token=token, recursive=recursive
        )

    def list_pages(
        self,
        section: Optional[str] = None,
        notebook: Optional[str] = None,
        sort_by: str = "order",
        reverse: bool = False,
    ) -> List[PageDTO]:
        """Fetch pages of a section, using configured defaults if parameters are omitted.
        
        Args:
            section: Section ID or name. If omitted, uses default section from settings.
            notebook: Optional notebook ID or name to scope section lookup. If omitted, uses default notebook.
            sort_by: Field to sort by ('order', 'title', 'modified', 'created').
            reverse: Sort order.
        """
        sec_target = section
        nb_target = notebook

        if not sec_target:
            def_sec = self.settings.get_default_section()
            if def_sec:
                sec_target = def_sec.get("id") or def_sec.get("name")
                if not nb_target:
                    nb_target = def_sec.get("notebook_id") or def_sec.get("notebook_name")
            else:
                raise ValueError(
                    "Nenhuma seção informada e nenhuma seção padrão configurada. "
                    "Use 'onebridge list-pages <secao>' ou configure uma padrão com 'onebridge set-section <secao>'."
                )

        if not nb_target:
            def_nb = self.settings.get_default_notebook()
            if def_nb:
                nb_target = def_nb.get("id") or def_nb.get("name")

        token = self.auth.get_valid_token()
        return self.catalog_service.list_pages(
            section_id_or_name=sec_target,
            token=token,
            notebook_id_or_name=nb_target,
            sort_by=sort_by,
            reverse=reverse,
        )

    def get_page(self, page_id: str) -> PageDTO:
        """Fetch details of a specific page by ID."""
        token = self.auth.get_valid_token()
        return self.catalog_service.get_page(page_id=page_id, token=token)

    def set_default_notebook(self, notebook: str) -> NotebookDTO:
        """Resolve and persist default notebook in settings."""
        token = self.auth.get_valid_token()
        nb = self.catalog_service.resolve_notebook(notebook_id_or_name=notebook, token=token)
        self.settings.set_default_notebook(notebook_id=nb.id, notebook_name=nb.name)
        return nb

    def set_default_section(
        self,
        section: str,
        notebook: Optional[str] = None,
    ) -> SectionDTO:
        """Resolve and persist default section in settings."""
        token = self.auth.get_valid_token()
        nb_context = notebook
        if not nb_context:
            def_nb = self.settings.get_default_notebook()
            if def_nb:
                nb_context = def_nb.get("id") or def_nb.get("name")

        sec = self.catalog_service.resolve_section(
            section_id_or_name=section,
            token=token,
            notebook_id_or_name=nb_context,
        )
        self.settings.set_default_section(
            section_id=sec.id,
            section_name=sec.name,
            notebook_id=sec.parent_notebook_id,
        )
        return sec

    def get_defaults(self) -> Dict[str, Any]:
        """Retrieve all currently configured defaults."""
        return self.settings.get_all_defaults()

    def clear_defaults(self, target: Optional[str] = None) -> None:
        """Clear configured defaults ('notebook', 'section', or all)."""
        if target == "notebook":
            self.settings.clear_default_notebook()
        elif target == "section":
            self.settings.clear_default_section()
        else:
            self.settings.clear_all_defaults()

    def fetch_page(
        self,
        page: str,
        section: Optional[str] = None,
        notebook: Optional[str] = None,
        output_dir: Optional[Union[str, Path]] = None,
        overwrite: bool = True,
        delay_ms: Optional[int] = None,
    ) -> PageExportResultDTO:
        """Fetch and export a single OneNote page to Markdown format.
        
        Args:
            page: Page ID or title.
            section: Section ID or name (optional scope).
            notebook: Notebook ID or name (optional scope).
            output_dir: Root directory where ARQUIVOS/ will be created.
            overwrite: Whether to overwrite existing markdown files.
            delay_ms: Delay in milliseconds between consecutive HTTP requests.
        """
        token = self.auth.get_valid_token()

        sec_target = section
        nb_target = notebook

        if not sec_target and not nb_target:
            def_sec = self.settings.get_default_section()
            if def_sec:
                sec_target = def_sec.get("id") or def_sec.get("name")
                nb_target = def_sec.get("notebook_id") or def_sec.get("notebook_name")

        if not nb_target:
            def_nb = self.settings.get_default_notebook()
            if def_nb:
                nb_target = def_nb.get("id") or def_nb.get("name")

        return self.export_service.export_page(
            page_id_or_title=page,
            token=token,
            section=sec_target,
            notebook=nb_target,
            output_dir=output_dir,
            overwrite=overwrite,
            delay_ms=delay_ms,
        )

    def fetch_pages(
        self,
        notebook: Optional[str] = None,
        section: Optional[str] = None,
        recursive: bool = True,
        output_dir: Optional[Union[str, Path]] = None,
        overwrite: bool = True,
        delay_ms: Optional[int] = None,
        on_progress: Optional[Callable[[PageExportResultDTO, int, int], None]] = None,
    ) -> BatchExportResultDTO:
        """Fetch and export multiple OneNote pages to Markdown format.
        
        Args:
            notebook: Notebook ID or name.
            section: Section ID or name.
            recursive: If True, recursively export pages from all nested section groups.
            output_dir: Root directory where ARQUIVOS/ will be created.
            overwrite: Whether to overwrite existing files.
            delay_ms: Delay in milliseconds between consecutive HTTP requests.
            on_progress: Optional callback invoked after each page is processed.
        """
        token = self.auth.get_valid_token()

        nb_target = notebook
        sec_target = section

        # Fallback to configured defaults if both are omitted
        if not nb_target and not sec_target:
            def_sec = self.settings.get_default_section()
            if def_sec:
                sec_target = def_sec.get("id") or def_sec.get("name")
                nb_target = def_sec.get("notebook_id") or def_sec.get("notebook_name")
            else:
                def_nb = self.settings.get_default_notebook()
                if def_nb:
                    nb_target = def_nb.get("id") or def_nb.get("name")
                else:
                    raise ValueError(
                        "Nenhum caderno ou seção informado e nenhum padrão configurado. "
                        "Informe '--notebook <nome>' ou '--section <nome>', ou configure com 'onebridge set-notebook'."
                    )

        return self.export_service.export_pages(
            token=token,
            notebook=nb_target,
            section=sec_target,
            recursive=recursive,
            output_dir=output_dir,
            overwrite=overwrite,
            delay_ms=delay_ms,
            on_progress=on_progress,
        )


