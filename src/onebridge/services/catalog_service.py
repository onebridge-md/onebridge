from typing import Any, Dict, List, Optional, Tuple

from onebridge.api.dto import (
    NotebookDTO,
    NotebookTreeDTO,
    PageDTO,
    SectionDTO,
    SectionGroupDTO,
)
from onebridge.core.graph_client import GraphNotFoundError, OneNoteGraphClient
from onebridge.logger import get_logger

logger = get_logger("onebridge.services.catalog_service")


class CatalogService:
    """Service for querying and navigating OneNote catalog resources."""

    def __init__(self, graph_client: Optional[OneNoteGraphClient] = None):
        self.graph_client = graph_client or OneNoteGraphClient()

    def list_notebooks(
        self,
        token: str,
        sort_by: str = "modified",
        reverse: bool = True,
    ) -> List[NotebookDTO]:
        """Fetch and return all user notebooks as DTOs, sorted by specified field."""
        logger.debug("Consultando lista de cadernos no Microsoft Graph...")
        raw_items = self.graph_client.get_notebooks(token=token)
        notebooks = [NotebookDTO.from_graph_dict(item) for item in raw_items]
        logger.info(f"Total de cadernos recuperados: {len(notebooks)}")

        if sort_by == "name":
            notebooks.sort(key=lambda nb: (nb.name or "").lower(), reverse=reverse)
        elif sort_by == "created":
            notebooks.sort(key=lambda nb: nb.created_at or "", reverse=reverse)
        else:  # default 'modified'
            notebooks.sort(key=lambda nb: nb.modified_at or "", reverse=reverse)

        return notebooks

    def get_notebook(self, notebook_id: str, token: str) -> NotebookDTO:
        """Fetch a specific notebook by ID."""
        logger.debug(f"Consultando caderno específico por ID: {notebook_id}")
        raw_item = self.graph_client.get_notebook(notebook_id=notebook_id, token=token)
        return NotebookDTO.from_graph_dict(raw_item)

    def resolve_notebook(self, notebook_id_or_name: str, token: str) -> NotebookDTO:
        """Resolve a notebook by its exact ID or by displayName (case-insensitive)."""
        logger.debug(f"Resolvendo caderno: '{notebook_id_or_name}'")
        # 1. Try direct ID fetch first
        try:
            nb = self.get_notebook(notebook_id=notebook_id_or_name, token=token)
            logger.debug(f"Caderno resolvido por ID direto: {nb.name} ({nb.id})")
            return nb
        except (GraphNotFoundError, Exception):
            pass

        # 2. Fallback: Search among all user notebooks by ID or Name
        all_notebooks = self.list_notebooks(token=token)
        target = notebook_id_or_name.strip().lower()

        # Exact ID match
        for nb in all_notebooks:
            if nb.id.lower() == target:
                return nb

        # Exact Name match (case-insensitive)
        for nb in all_notebooks:
            if (nb.name or "").strip().lower() == target:
                return nb

        # Partial Name match (case-insensitive)
        for nb in all_notebooks:
            if target in (nb.name or "").lower():
                return nb

        raise GraphNotFoundError(
            f"Caderno '{notebook_id_or_name}' não encontrado no OneNote do usuário."
        )

    def _build_section_group_tree(
        self, sg_data: Dict[str, Any], token: str, parent_path: str = ""
    ) -> SectionGroupDTO:
        """Recursively fetch and build SectionGroup hierarchy with nested sections and subgroups."""
        group_dto = SectionGroupDTO.from_graph_dict(sg_data, parent_path=parent_path)
        current_path = f"{parent_path} / {group_dto.name}" if parent_path else group_dto.name

        # 1. Fetch sections within this section group
        raw_sections = self.graph_client.get_section_group_sections(
            section_group_id=group_dto.id, token=token
        )
        group_dto.sections = [
            SectionDTO.from_graph_dict(s, parent_path=current_path) for s in raw_sections
        ]

        # 2. Fetch nested section groups (subsections) recursively
        raw_subgroups = self.graph_client.get_section_group_section_groups(
            section_group_id=group_dto.id, token=token
        )
        group_dto.section_groups = [
            self._build_section_group_tree(sub_sg, token=token, parent_path=current_path)
            for sub_sg in raw_subgroups
        ]

        return group_dto

    def list_section_group_sections(
        self, section_group_id: str, token: str, parent_path: str = ""
    ) -> List[SectionDTO]:
        """Fetch direct sections within a specific section group."""
        raw_sections = self.graph_client.get_section_group_sections(
            section_group_id=section_group_id, token=token
        )
        return [
            SectionDTO.from_graph_dict(s, parent_path=parent_path) for s in raw_sections
        ]

    def list_section_group_section_groups(
        self, section_group_id: str, token: str, parent_path: str = ""
    ) -> List[SectionGroupDTO]:
        """Fetch direct child section groups within a specific section group."""
        raw_subgroups = self.graph_client.get_section_group_section_groups(
            section_group_id=section_group_id, token=token
        )
        return [
            SectionGroupDTO.from_graph_dict(g, parent_path=parent_path) for g in raw_subgroups
        ]

    def list_sections_in_section_group(
        self, section_group_id: str, token: str, recursive: bool = True
    ) -> List[SectionDTO]:
        """Fetch all sections within a section group, optionally traversing nested subgroups recursively."""
        sections = self.list_section_group_sections(section_group_id=section_group_id, token=token)
        if not recursive:
            return sections

        result = list(sections)
        subgroups = self.list_section_group_section_groups(section_group_id=section_group_id, token=token)
        for sg in subgroups:
            result.extend(
                self.list_sections_in_section_group(sg.id, token=token, recursive=True)
            )
        return result

    def get_notebook_tree(self, notebook_id_or_name: str, token: str) -> NotebookTreeDTO:
        """Fetch the full hierarchical tree of a notebook including all sections and nested section groups."""
        notebook = self.resolve_notebook(notebook_id_or_name, token=token)

        # 1. Direct sections under notebook
        raw_direct_sections = self.graph_client.get_notebook_sections(
            notebook_id=notebook.id, token=token
        )
        direct_sections = [
            SectionDTO.from_graph_dict(s, parent_path="") for s in raw_direct_sections
        ]

        # 2. Direct section groups under notebook (resolved recursively)
        raw_direct_groups = self.graph_client.get_notebook_section_groups(
            notebook_id=notebook.id, token=token
        )
        section_groups = [
            self._build_section_group_tree(sg, token=token, parent_path="")
            for sg in raw_direct_groups
        ]

        return NotebookTreeDTO(
            notebook=notebook,
            sections=direct_sections,
            section_groups=section_groups,
        )

    def list_sections(
        self,
        notebook_id_or_name: str,
        token: str,
        recursive: bool = True,
        sort_by: str = "name",
        reverse: bool = False,
    ) -> List[SectionDTO]:
        """Fetch sections of a notebook. If recursive=True, traverses all nested section groups.
        
        Args:
            notebook_id_or_name: ID or displayName of the notebook.
            token: OAuth Bearer token.
            recursive: If True, recursively includes sections inside all subsection groups.
            sort_by: Field to sort by ('name', 'modified', 'created', 'path').
            reverse: Sort order.
        """
        if not recursive:
            notebook = self.resolve_notebook(notebook_id_or_name, token=token)
            raw_sections = self.graph_client.get_notebook_sections(
                notebook_id=notebook.id, token=token
            )
            sections = [SectionDTO.from_graph_dict(s, parent_path="") for s in raw_sections]
        else:
            tree = self.get_notebook_tree(notebook_id_or_name, token=token)
            sections = self._flatten_sections_from_tree(tree)

        # Sorting
        if sort_by == "modified":
            sections.sort(key=lambda s: s.modified_at or "", reverse=reverse)
        elif sort_by == "created":
            sections.sort(key=lambda s: s.created_at or "", reverse=reverse)
        elif sort_by == "path":
            sections.sort(
                key=lambda s: (f"{s.parent_path or ''}/{s.name or ''}").lower(),
                reverse=reverse,
            )
        else:  # default 'name'
            sections.sort(key=lambda s: (s.name or "").lower(), reverse=reverse)

        return sections

    def _flatten_sections_from_tree(self, tree: NotebookTreeDTO) -> List[SectionDTO]:
        """Helper to extract a flat list of all sections from a notebook tree."""
        result: List[SectionDTO] = list(tree.sections)

        def _collect(groups: List[SectionGroupDTO]):
            for group in groups:
                if group.sections:
                    result.extend(group.sections)
                if group.section_groups:
                    _collect(group.section_groups)

        _collect(tree.section_groups)
        return result

    def get_section(self, section_id: str, token: str) -> SectionDTO:
        """Fetch a specific section by ID."""
        raw_item = self.graph_client.get_section(section_id=section_id, token=token)
        return SectionDTO.from_graph_dict(raw_item)

    def resolve_section(
        self,
        section_id_or_name: str,
        token: str,
        notebook_id_or_name: Optional[str] = None,
    ) -> SectionDTO:
        """Resolve a section by its ID or displayName, optionally scoped to a specific notebook."""
        # 1. Try direct ID fetch first
        try:
            return self.get_section(section_id=section_id_or_name, token=token)
        except (GraphNotFoundError, Exception):
            pass

        target = section_id_or_name.strip().lower()

        # 2. If notebook context is provided, search exclusively in that notebook
        if notebook_id_or_name:
            candidate_sections = self.list_sections(
                notebook_id_or_name=notebook_id_or_name,
                token=token,
                recursive=True,
            )
        else:
            # Search across all notebooks
            candidate_sections = []
            all_notebooks = self.list_notebooks(token=token)
            for nb in all_notebooks:
                try:
                    candidate_sections.extend(
                        self.list_sections(notebook_id_or_name=nb.id, token=token, recursive=True)
                    )
                except Exception:
                    pass

        # Match exact ID
        for s in candidate_sections:
            if s.id.lower() == target:
                return s

        # Match exact Name (case-insensitive)
        for s in candidate_sections:
            if (s.name or "").strip().lower() == target:
                return s

        # Match partial Name (case-insensitive)
        for s in candidate_sections:
            if target in (s.name or "").lower():
                return s

        context_info = f" no caderno '{notebook_id_or_name}'" if notebook_id_or_name else ""
        raise GraphNotFoundError(
            f"Seção '{section_id_or_name}' não encontrada{context_info} no OneNote do usuário."
        )

    def list_pages(
        self,
        section_id_or_name: str,
        token: str,
        notebook_id_or_name: Optional[str] = None,
        sort_by: str = "order",
        reverse: bool = False,
    ) -> List[PageDTO]:
        """Fetch pages of a section.
        
        Args:
            section_id_or_name: ID or displayName of the section.
            token: OAuth Bearer token.
            notebook_id_or_name: Optional notebook ID or name to scope search.
            sort_by: Field to sort by ('order', 'title', 'modified', 'created').
            reverse: Sort order.
        """
        section = self.resolve_section(
            section_id_or_name=section_id_or_name,
            token=token,
            notebook_id_or_name=notebook_id_or_name,
        )

        raw_pages = self.graph_client.get_section_pages(section_id=section.id, token=token)
        pages = [PageDTO.from_graph_dict(p, parent_section_name=section.name) for p in raw_pages]

        # Sorting
        if sort_by == "title":
            pages.sort(key=lambda p: (p.title or "").lower(), reverse=reverse)
        elif sort_by == "modified":
            pages.sort(key=lambda p: p.modified_at or "", reverse=reverse)
        elif sort_by == "created":
            pages.sort(key=lambda p: p.created_at or "", reverse=reverse)
        else:  # default 'order'
            pages.sort(key=lambda p: p.order, reverse=reverse)

        return pages

    def get_page(self, page_id: str, token: str) -> PageDTO:
        """Fetch a specific page by ID."""
        raw_item = self.graph_client.get_page(page_id=page_id, token=token)
        return PageDTO.from_graph_dict(raw_item)

    def resolve_page(
        self,
        page_id_or_title: str,
        token: str,
        section_id_or_name: Optional[str] = None,
        notebook_id_or_name: Optional[str] = None,
    ) -> PageDTO:
        """Resolves a page by ID or Title (case-insensitive / partial match).
        
        Args:
            page_id_or_title: Page ID or title string.
            token: OAuth Bearer token.
            section_id_or_name: Optional section to scope search.
            notebook_id_or_name: Optional notebook to scope search.
        """
        # 1. Try direct ID fetch first
        try:
            return self.get_page(page_id=page_id_or_title, token=token)
        except (GraphNotFoundError, Exception):
            pass

        target = page_id_or_title.strip().lower()

        # 2. Determine candidate sections to search in
        candidate_sections: List[SectionDTO] = []
        if section_id_or_name:
            sec = self.resolve_section(
                section_id_or_name=section_id_or_name,
                token=token,
                notebook_id_or_name=notebook_id_or_name,
            )
            candidate_sections = [sec]
        elif notebook_id_or_name:
            candidate_sections = self.list_sections(
                notebook_id_or_name=notebook_id_or_name,
                token=token,
                recursive=True,
            )
        else:
            # All notebooks
            notebooks = self.list_notebooks(token=token)
            for nb in notebooks:
                try:
                    candidate_sections.extend(
                        self.list_sections(notebook_id_or_name=nb.id, token=token, recursive=True)
                    )
                except Exception:
                    pass

        # Search pages in candidate sections
        all_pages: List[PageDTO] = []
        for sec in candidate_sections:
            try:
                raw_pages = self.graph_client.get_section_pages(section_id=sec.id, token=token)
                all_pages.extend(
                    [PageDTO.from_graph_dict(p, parent_section_name=sec.name) for p in raw_pages]
                )
            except Exception:
                pass

        # Exact ID match
        for p in all_pages:
            if p.id.lower() == target:
                return p

        # Exact Title match (case-insensitive)
        for p in all_pages:
            if (p.title or "").strip().lower() == target:
                return p

        # Partial Title match (case-insensitive)
        for p in all_pages:
            if target in (p.title or "").lower():
                return p

        context_info = ""
        if section_id_or_name:
            context_info = f" na seção '{section_id_or_name}'"
        elif notebook_id_or_name:
            context_info = f" no caderno '{notebook_id_or_name}'"

        raise GraphNotFoundError(
            f"Página '{page_id_or_title}' não encontrada{context_info} no OneNote do usuário."
        )

    def get_page_hierarchy(
        self,
        page: PageDTO,
        token: str,
    ) -> Tuple[NotebookDTO, SectionDTO, Optional[str]]:
        """Resolves the full parent hierarchy (Notebook, Section, parent_path) for a page."""
        if not page.parent_section_id:
            # Fallback if section ID not in DTO
            raw_page = self.graph_client.get_page(page.id, token=token)
            parent_sec = raw_page.get("parentSection", {})
            section_id = parent_sec.get("id") if isinstance(parent_sec, dict) else None
        else:
            section_id = page.parent_section_id

        if not section_id:
            raise GraphNotFoundError(f"Não foi possível identificar a seção pai da página '{page.title}'.")

        section = self.get_section(section_id=section_id, token=token)

        # Resolve parent notebook
        notebook_id = section.parent_notebook_id
        if not notebook_id:
            # If section belongs to section group, traverse up
            notebook_id = "default_notebook"
            notebook = NotebookDTO(id=notebook_id, name="OneNote")
        else:
            notebook = self.get_notebook(notebook_id=notebook_id, token=token)

        parent_path = section.parent_path
        return notebook, section, parent_path


