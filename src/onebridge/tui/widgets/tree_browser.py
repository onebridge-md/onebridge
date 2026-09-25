"""TreeBrowser widget with vim navigation and multi-selection checkboxes."""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set, Self

from rich.text import Text
from textual import on
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Tree
from textual.widgets.tree import TreeNode

from onebridge.api.dto import NotebookDTO, PageDTO, SectionDTO, SectionGroupDTO
from onebridge.logger import get_logger

logger = get_logger("onebridge.tui.widgets.tree_browser")


@dataclass
class NodeData:
    """Metadata associated with a tree node."""

    node_type: str  # 'notebook', 'section_group', 'section', 'page', 'loading', 'empty', 'error'
    id: str
    name: str
    dto: Any = None
    checked: bool = False
    loaded: bool = False
    loading: bool = False
    loading_message: str = ""
    parent_notebook_id: Optional[str] = None
    parent_notebook_name: Optional[str] = None
    parent_section_id: Optional[str] = None
    parent_section_name: Optional[str] = None
    parent_path: Optional[str] = None


class TreeBrowser(Tree[NodeData]):
    """Hierarchical tree browser with Vim navigation (h, j, k, l) and checkboxes."""

    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    BINDINGS = [
        Binding("j", "cursor_down", "Baixo (j)", show=False),
        Binding("k", "cursor_up", "Cima (k)", show=False),
        Binding("h", "collapse_or_parent", "Fechar/Pai (h)"),
        Binding("l", "expand_or_child", "Abrir/Filho (l)"),
        Binding("enter", "expand_or_child", "Abrir/Filho (Enter)", show=False),
        Binding("space", "toggle_check", "Marcar/Desmarcar (Espaço)"),
        Binding("a", "toggle_all", "Marcar/Desmarcar Todos (a)"),
    ]

    class NodeSelectionChanged(Message):
        """Emitted when checked state changes or cursor moves."""

        def __init__(self, selected_count: int, current_node: Optional[TreeNode[NodeData]] = None):
            super().__init__()
            self.selected_count = selected_count
            self.current_node = current_node

    class NodeExpansionRequested(Message):
        """Emitted when a node needs async data loading."""

        def __init__(self, node: TreeNode[NodeData]):
            super().__init__()
            self.node = node

    def __init__(
        self,
        label: str = "Cadernos OneNote",
        *,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ):
        super().__init__(label=label, data=NodeData(node_type="root", id="root", name=label), name=name, id=id, classes=classes)
        self.show_root = False
        self.auto_expand = False
        self.guide_depth = 3
        self._spinner_frame: int = 0
        self._spinner_timer = None
        self._loading_nodes: Set[TreeNode[NodeData]] = set()

    @classmethod
    def format_node_label(cls, data: NodeData, spinner_char: Optional[str] = None) -> Text:
        """Format node label with checkbox, icon, name, and spinner/hourglass."""
        char = spinner_char or cls.SPINNER_FRAMES[0]

        if data.node_type == "loading":
            text = Text()
            text.append(f"   ⏳ {char} ", style="bold yellow")
            text.append(data.name, style="italic dim yellow")
            return text

        if data.node_type == "empty":
            text = Text()
            text.append("   • ", style="dim")
            text.append(data.name, style="italic dim")
            return text

        if data.node_type == "error":
            text = Text()
            text.append("   ✖ ", style="bold red")
            text.append(data.name, style="red")
            return text

        check_symbol = "[x] " if data.checked else "[ ] "
        check_style = "bold green" if data.checked else "dim"

        icons = {
            "notebook": ("📓 ", "bold magenta"),
            "section_group": ("📁 ", "bold yellow"),
            "section": ("📑 ", "bold cyan"),
            "page": ("📄 ", "white"),
        }

        icon, icon_style = icons.get(data.node_type, ("• ", "white"))

        text = Text()
        text.append(check_symbol, style=check_style)
        text.append(icon, style=icon_style)
        text.append(data.name, style="bold" if data.node_type in ("notebook", "section") else "")

        if data.loading:
            text.append(f"  ⏳ {char}", style="bold yellow")

        return text

    @property
    def current_spinner_char(self) -> str:
        """Return the current spinning wheel frame character."""
        return self.SPINNER_FRAMES[self._spinner_frame % len(self.SPINNER_FRAMES)]

    @property
    def has_loading_nodes(self) -> bool:
        """Check if any node is currently loading."""
        return len(self._loading_nodes) > 0

    def set_node_loading(
        self,
        node: TreeNode[NodeData],
        is_loading: bool,
        message: str = "Carregando...",
    ) -> Optional[TreeNode[NodeData]]:
        """Mark a node as loading or completed, updating label and temporary loading child."""
        if not node.data:
            return None

        if is_loading:
            node.data.loading = True
            node.data.loading_message = message
            self._loading_nodes.add(node)

            char = self.current_spinner_char
            node.set_label(self.format_node_label(node.data, spinner_char=char))

            # Add or update temporary loading child
            existing_loading = [
                c for c in node.children if c.data and c.data.node_type == "loading"
            ]
            if existing_loading:
                loading_child = existing_loading[0]
                loading_child.set_label(self.format_node_label(loading_child.data, spinner_char=char))
            else:
                loading_data = NodeData(
                    node_type="loading",
                    id=f"loading-{node.data.id}",
                    name=message,
                    loaded=True,
                )
                loading_child = node.add_leaf(
                    label=self.format_node_label(loading_data, spinner_char=char),
                    data=loading_data,
                )

            # Start timer if mounted and not already running
            if self._spinner_timer is None and getattr(self, "is_mounted", False):
                try:
                    self._spinner_timer = self.set_interval(0.1, self._tick_spinner)
                except Exception:
                    pass

            return loading_child

        else:
            node.data.loading = False
            node.data.loading_message = ""
            self._loading_nodes.discard(node)

            # Remove loading children
            for child in list(node.children):
                if child.data and child.data.node_type == "loading":
                    child.remove()

            node.set_label(self.format_node_label(node.data))

            if not self._loading_nodes and self._spinner_timer is not None:
                try:
                    self._spinner_timer.stop()
                except Exception:
                    pass
                self._spinner_timer = None

            return None

    def _tick_spinner(self) -> None:
        """Advance spinner animation frame and refresh labels of all loading nodes."""
        if not self._loading_nodes:
            if self._spinner_timer is not None:
                try:
                    self._spinner_timer.stop()
                except Exception:
                    pass
                self._spinner_timer = None
            return

        self._spinner_frame = (self._spinner_frame + 1) % len(self.SPINNER_FRAMES)
        char = self.SPINNER_FRAMES[self._spinner_frame]

        for node in list(self._loading_nodes):
            if node.data and node.data.loading:
                node.set_label(self.format_node_label(node.data, spinner_char=char))
                for child in node.children:
                    if child.data and child.data.node_type == "loading":
                        child.set_label(self.format_node_label(child.data, spinner_char=char))

    def clear(self) -> Self:
        """Clear tree nodes and stop spinner timer."""
        if self._spinner_timer is not None:
            try:
                self._spinner_timer.stop()
            except Exception:
                pass
            self._spinner_timer = None
        self._loading_nodes.clear()
        return super().clear()

    def on_unmount(self) -> None:
        """Stop spinner timer on unmount."""
        if self._spinner_timer is not None:
            try:
                self._spinner_timer.stop()
            except Exception:
                pass
            self._spinner_timer = None
        self._loading_nodes.clear()

    @on(Tree.NodeExpanded)
    def _on_tree_node_expanded(self, event: Tree.NodeExpanded) -> None:
        """Handle tree node expansion (via mouse click or keyboard)."""
        node = event.node
        if (
            node.data
            and not node.data.loaded
            and not node.data.loading
            and node.data.node_type in ("notebook", "section_group", "section")
        ):
            self.post_message(self.NodeExpansionRequested(node))

    def action_collapse_or_parent(self) -> None:
        """Vim 'h': collapse node if expanded, otherwise navigate to parent node."""
        node = self.cursor_node
        if node is None:
            return

        if node.is_expanded and len(node.children) > 0:
            node.collapse()
        elif node.parent and node.parent != self.root:
            self.select_node(node.parent)

    def action_expand_or_child(self) -> None:
        """Vim 'l': expand node if collapsed; if already expanded, navigate to first child."""
        node = self.cursor_node
        if node is None:
            return

        if not node.is_expanded:
            if (
                not node.data.loaded
                and not node.data.loading
                and node.data.node_type in ("notebook", "section_group", "section")
            ):
                self.post_message(self.NodeExpansionRequested(node))
            node.expand()
        elif not (node.data and node.data.loading) and len(node.children) > 0:
            self.select_node(node.children[0])

    def action_toggle_check(self) -> None:
        """Toggle checkbox of current node and cascade to children."""
        node = self.cursor_node
        if node is None or node.data is None or node.data.node_type in ("root", "loading", "empty", "error"):
            return

        new_state = not node.data.checked
        self._set_node_check(node, new_state, cascade=True)
        self.post_message(self.NodeSelectionChanged(self.count_selected(), node))

    def action_toggle_all(self) -> None:
        """Toggle checked state for all top-level nodes."""
        valid_children = [
            child
            for child in self.root.children
            if child.data and child.data.node_type not in ("loading", "empty", "error")
        ]
        all_checked = all(child.data.checked for child in valid_children) if valid_children else False
        new_state = not all_checked
        for child in valid_children:
            self._set_node_check(child, new_state, cascade=True)
        self.post_message(self.NodeSelectionChanged(self.count_selected(), self.cursor_node))

    def _set_node_check(self, node: TreeNode[NodeData], state: bool, cascade: bool = True) -> None:
        """Recursively update checked state and label."""
        if node.data and node.data.node_type not in ("loading", "empty", "error"):
            node.data.checked = state
            node.set_label(self.format_node_label(node.data, spinner_char=self.current_spinner_char))

        if cascade:
            for child in node.children:
                if child.data and child.data.node_type not in ("loading", "empty", "error"):
                    self._set_node_check(child, state, cascade=True)

    def add_notebook_node(self, notebook: NotebookDTO) -> TreeNode[NodeData]:
        """Add a notebook to the tree root."""
        data = NodeData(
            node_type="notebook",
            id=notebook.id,
            name=notebook.name,
            dto=notebook,
            checked=False,
            loaded=False,
        )
        return self.root.add(
            label=self.format_node_label(data),
            data=data,
            expand=False,
        )

    def add_section_group_node(
        self,
        parent_node: TreeNode[NodeData],
        group: SectionGroupDTO,
        notebook_id: str,
        notebook_name: str,
        parent_path: Optional[str] = None,
    ) -> TreeNode[NodeData]:
        """Add a section group node to parent."""
        data = NodeData(
            node_type="section_group",
            id=group.id,
            name=group.name,
            dto=group,
            checked=parent_node.data.checked if parent_node.data else False,
            loaded=False,
            parent_notebook_id=notebook_id,
            parent_notebook_name=notebook_name,
            parent_path=parent_path,
        )
        return parent_node.add(
            label=self.format_node_label(data),
            data=data,
            expand=False,
        )

    def add_section_node(
        self,
        parent_node: TreeNode[NodeData],
        section: SectionDTO,
        notebook_id: str,
        notebook_name: str,
        parent_path: Optional[str] = None,
    ) -> TreeNode[NodeData]:
        """Add a section node to parent."""
        data = NodeData(
            node_type="section",
            id=section.id,
            name=section.name,
            dto=section,
            checked=parent_node.data.checked if parent_node.data else False,
            loaded=False,
            parent_notebook_id=notebook_id,
            parent_notebook_name=notebook_name,
            parent_path=parent_path,
        )
        return parent_node.add(
            label=self.format_node_label(data),
            data=data,
            expand=False,
        )

    def add_page_node(
        self,
        parent_node: TreeNode[NodeData],
        page: PageDTO,
        notebook_id: str,
        notebook_name: str,
        section_id: str,
        section_name: str,
        parent_path: Optional[str] = None,
    ) -> TreeNode[NodeData]:
        """Add a page node to section parent."""
        data = NodeData(
            node_type="page",
            id=page.id,
            name=page.title or "Sem Título",
            dto=page,
            checked=parent_node.data.checked if parent_node.data else False,
            loaded=True,
            parent_notebook_id=notebook_id,
            parent_notebook_name=notebook_name,
            parent_section_id=section_id,
            parent_section_name=section_name,
            parent_path=parent_path,
        )
        return parent_node.add_leaf(
            label=self.format_node_label(data),
            data=data,
        )

    def count_selected(self) -> int:
        """Count total selected items."""
        count = 0

        def _count(node: TreeNode[NodeData]):
            nonlocal count
            if (
                node.data
                and node.data.checked
                and node.data.node_type not in ("root", "loading", "empty", "error")
            ):
                count += 1
            for child in node.children:
                _count(child)

        _count(self.root)
        return count

    def get_selected_targets(self) -> List[NodeData]:
        """Return all distinct items currently selected."""
        selected: List[NodeData] = []

        def _collect(node: TreeNode[NodeData]):
            if (
                node.data
                and node.data.checked
                and node.data.node_type not in ("root", "loading", "empty", "error")
            ):
                selected.append(node.data)
            for child in node.children:
                _collect(child)

        _collect(self.root)
        return selected

    def watch_cursor_node(self, old_node: Optional[TreeNode[NodeData]], new_node: Optional[TreeNode[NodeData]]) -> None:
        """Notify listeners when cursor moves to a different node."""
        super().watch_cursor_node(old_node, new_node)
        self.post_message(self.NodeSelectionChanged(self.count_selected(), new_node))
