"""Data Transfer Objects (DTOs) for OneBridge API layer."""

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


@dataclass
class NotebookDTO:
    """Represents a Microsoft OneNote Notebook."""

    id: str
    name: str
    created_at: Optional[str] = None
    modified_at: Optional[str] = None
    is_default: bool = False
    user_role: str = "Owner"
    is_shared: bool = False
    sections_url: Optional[str] = None
    section_groups_url: Optional[str] = None
    web_url: Optional[str] = None
    client_url: Optional[str] = None

    @classmethod
    def from_graph_dict(cls, data: Dict[str, Any]) -> "NotebookDTO":
        """Factory method to construct NotebookDTO from Microsoft Graph JSON response."""
        links = data.get("links", {})
        web_link = links.get("oneNoteWebUrl", {}).get("href")
        client_link = links.get("oneNoteClientUrl", {}).get("href")

        return cls(
            id=data.get("id", ""),
            name=data.get("displayName", "Sem Título"),
            created_at=data.get("createdDateTime"),
            modified_at=data.get("lastModifiedDateTime"),
            is_default=data.get("isDefault", False),
            user_role=data.get("userRole", "Owner"),
            is_shared=data.get("isShared", False),
            sections_url=data.get("sectionsUrl"),
            section_groups_url=data.get("sectionGroupsUrl"),
            web_url=web_link,
            client_url=client_link,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert DTO to serializable dictionary."""
        return asdict(self)


@dataclass
class UserProfileDTO:
    """Represents the authenticated Microsoft user profile."""

    id: str
    name: str
    email: str

    @classmethod
    def from_graph_dict(cls, data: Dict[str, Any]) -> "UserProfileDTO":
        """Factory method to construct UserProfileDTO from /me response."""
        email = data.get("mail") or data.get("userPrincipalName", "")
        name = data.get("displayName", "N/A")
        user_id = data.get("id", "")
        return cls(id=user_id, name=name, email=email)

    def to_dict(self) -> Dict[str, Any]:
        """Convert DTO to serializable dictionary."""
        return asdict(self)


@dataclass
class SectionDTO:
    """Represents a Microsoft OneNote Section."""

    id: str
    name: str
    created_at: Optional[str] = None
    modified_at: Optional[str] = None
    is_default: bool = False
    pages_url: Optional[str] = None
    parent_notebook_id: Optional[str] = None
    parent_section_group_id: Optional[str] = None
    parent_path: Optional[str] = None
    web_url: Optional[str] = None
    client_url: Optional[str] = None

    @classmethod
    def from_graph_dict(cls, data: Dict[str, Any], parent_path: Optional[str] = None) -> "SectionDTO":
        """Factory method to construct SectionDTO from Microsoft Graph JSON response."""
        links = data.get("links", {})
        web_link = links.get("oneNoteWebUrl", {}).get("href")
        client_link = links.get("oneNoteClientUrl", {}).get("href")

        parent_nb = data.get("parentNotebook")
        parent_nb_id = parent_nb.get("id") if isinstance(parent_nb, dict) else parent_nb

        parent_sg = data.get("parentSectionGroup")
        parent_sg_id = parent_sg.get("id") if isinstance(parent_sg, dict) else parent_sg

        return cls(
            id=data.get("id", ""),
            name=data.get("displayName", "Sem Título"),
            created_at=data.get("createdDateTime"),
            modified_at=data.get("lastModifiedDateTime"),
            is_default=data.get("isDefault", False),
            pages_url=data.get("pagesUrl"),
            parent_notebook_id=parent_nb_id,
            parent_section_group_id=parent_sg_id,
            parent_path=parent_path,
            web_url=web_link,
            client_url=client_link,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert DTO to serializable dictionary."""
        return asdict(self)


@dataclass
class SectionGroupDTO:
    """Represents a Microsoft OneNote Section Group (subsection container)."""

    id: str
    name: str
    created_at: Optional[str] = None
    modified_at: Optional[str] = None
    parent_notebook_id: Optional[str] = None
    parent_section_group_id: Optional[str] = None
    parent_path: Optional[str] = None
    sections_url: Optional[str] = None
    section_groups_url: Optional[str] = None
    sections: Optional[list] = None
    section_groups: Optional[list] = None
    web_url: Optional[str] = None
    client_url: Optional[str] = None

    def __post_init__(self):
        if self.sections is None:
            self.sections = []
        if self.section_groups is None:
            self.section_groups = []

    @classmethod
    def from_graph_dict(cls, data: Dict[str, Any], parent_path: Optional[str] = None) -> "SectionGroupDTO":
        """Factory method to construct SectionGroupDTO from Microsoft Graph JSON response."""
        links = data.get("links", {})
        web_link = links.get("oneNoteWebUrl", {}).get("href")
        client_link = links.get("oneNoteClientUrl", {}).get("href")

        parent_nb = data.get("parentNotebook")
        parent_nb_id = parent_nb.get("id") if isinstance(parent_nb, dict) else parent_nb

        parent_sg = data.get("parentSectionGroup")
        parent_sg_id = parent_sg.get("id") if isinstance(parent_sg, dict) else parent_sg

        return cls(
            id=data.get("id", ""),
            name=data.get("displayName", "Sem Título"),
            created_at=data.get("createdDateTime"),
            modified_at=data.get("lastModifiedDateTime"),
            parent_notebook_id=parent_nb_id,
            parent_section_group_id=parent_sg_id,
            parent_path=parent_path,
            sections_url=data.get("sectionsUrl"),
            section_groups_url=data.get("sectionGroupsUrl"),
            sections=[],
            section_groups=[],
            web_url=web_link,
            client_url=client_link,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert DTO and its nested children to serializable dictionary."""
        res = asdict(self)
        return res


@dataclass
class NotebookTreeDTO:
    """Represents a hierarchical tree of a Notebook and all its sections/subgroups."""

    notebook: NotebookDTO
    sections: list  # List[SectionDTO]
    section_groups: list  # List[SectionGroupDTO]

    def to_dict(self) -> Dict[str, Any]:
        """Convert tree to serializable dictionary."""
        return {
            "notebook": self.notebook.to_dict(),
            "sections": [s.to_dict() for s in self.sections],
            "section_groups": [sg.to_dict() for sg in self.section_groups],
        }


@dataclass
class PageDTO:
    """Represents a Microsoft OneNote Page."""

    id: str
    title: str
    created_at: Optional[str] = None
    modified_at: Optional[str] = None
    level: int = 0
    order: int = 0
    parent_section_id: Optional[str] = None
    parent_section_name: Optional[str] = None
    content_url: Optional[str] = None
    web_url: Optional[str] = None
    client_url: Optional[str] = None

    @classmethod
    def from_graph_dict(
        cls, data: Dict[str, Any], parent_section_name: Optional[str] = None
    ) -> "PageDTO":
        """Factory method to construct PageDTO from Microsoft Graph JSON response."""
        links = data.get("links", {})
        web_link = links.get("oneNoteWebUrl", {}).get("href")
        client_link = links.get("oneNoteClientUrl", {}).get("href")

        parent_sec = data.get("parentSection") or {}
        parent_sec_id = parent_sec.get("id") if isinstance(parent_sec, dict) else None
        parent_sec_name = (
            parent_section_name
            or (parent_sec.get("displayName") if isinstance(parent_sec, dict) else None)
        )

        level_val = data.get("level", 0)
        try:
            level = int(level_val) if level_val is not None else 0
        except (ValueError, TypeError):
            level = 0

        order_val = data.get("order", 0)
        try:
            order = int(order_val) if order_val is not None else 0
        except (ValueError, TypeError):
            order = 0

        return cls(
            id=data.get("id", ""),
            title=data.get("title", "Sem Título"),
            created_at=data.get("createdDateTime"),
            modified_at=data.get("lastModifiedDateTime"),
            level=level,
            order=order,
            parent_section_id=parent_sec_id,
            parent_section_name=parent_sec_name,
            content_url=data.get("contentUrl"),
            web_url=web_link,
            client_url=client_link,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert DTO to serializable dictionary."""
        return asdict(self)


@dataclass
class PageExportResultDTO:
    """Represents the result of exporting a single OneNote page to Markdown."""

    page_id: str
    title: str
    file_path: str
    relative_path: str
    notebook_name: str
    section_name: str
    section_group: Optional[str] = None
    images_downloaded: int = 0
    attachments_downloaded: int = 0
    file_size_bytes: int = 0
    success: bool = True
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert DTO to serializable dictionary."""
        return asdict(self)


@dataclass
class BatchExportResultDTO:
    """Represents the aggregate result of a batch export operation."""

    total_pages: int
    successful_pages: int
    failed_pages: int
    total_images: int
    total_attachments: int
    output_directory: str
    results: list  # List[PageExportResultDTO]
    elapsed_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert DTO to serializable dictionary."""
        return {
            "total_pages": self.total_pages,
            "successful_pages": self.successful_pages,
            "failed_pages": self.failed_pages,
            "total_images": self.total_images,
            "total_attachments": self.total_attachments,
            "output_directory": self.output_directory,
            "results": [r.to_dict() for r in self.results],
            "elapsed_seconds": self.elapsed_seconds,
        }


