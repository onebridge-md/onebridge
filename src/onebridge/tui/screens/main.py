"""Main screen for OneBridge TUI with dual-pane layout and Vim navigation."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from rich.text import Text
from textual.widgets import Button, Footer, Header, Input, Label, LoadingIndicator, Static, Tree
from textual.widgets.tree import TreeNode

from onebridge.api.client import OneBridgeAPI
from onebridge.api.dto import NotebookDTO, PageDTO, SectionDTO, SectionGroupDTO
from onebridge.config import DEFAULT_EXPORT_DIR, DEFAULT_REQUEST_DELAY_MS
from onebridge.logger import get_logger, log_tui_error
from onebridge.tui.screens.error_modal import ErrorModal
from onebridge.tui.screens.export_complete_modal import ExportCompleteModal
from onebridge.tui.screens.login import LoginModal
from onebridge.tui.widgets.progress_panel import ExportTask, ProgressPanel
from onebridge.tui.widgets.tree_browser import NodeData, TreeBrowser

logger = get_logger("onebridge.tui.screens.main")


class MainScreen(Screen):
    """Main interactive screen of OneBridge."""

    BINDINGS = [
        Binding("e", "export_selected", "Exportar (e)", priority=True),
        Binding("r", "refresh_tree", "Recarregar (r)"),
        Binding("L", "open_login", "Conta/Login (L)"),
        Binding("q", "app.quit", "Sair (q)"),
    ]

    DEFAULT_CSS = """
    MainScreen {
        layout: vertical;
    }

    #main_container {
        height: 1fr;
        layout: horizontal;
    }

    #left_column {
        width: 55%;
        height: 100%;
        border-right: solid $primary;
        padding: 0 1;
    }

    #tree_browser {
        height: 1fr;
        background: $surface;
    }

    #right_column {
        width: 45%;
        height: 100%;
        padding: 0 1;
        layout: vertical;
    }

    #details_card {
        height: auto;
        max-height: 14;
        background: $surface;
        border: round $primary;
        padding: 1;
        margin-bottom: 1;
    }

    #card_title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    .detail_row {
        height: auto;
        color: $text-muted;
    }

    #actions_card {
        height: auto;
        background: $surface;
        border: round $secondary;
        padding: 1;
        margin-bottom: 1;
    }

    #actions_row {
        height: auto;
        margin-top: 1;
    }

    #actions_row Button {
        margin-right: 1;
    }

    #progress_container {
        height: 1fr;
    }

    #tree_loading {
        height: 3;
        display: none;
    }
    """

    def __init__(self, api: OneBridgeAPI):
        super().__init__()
        self.api = api
        self.is_exporting = False
        import threading
        self._export_lock = threading.Lock()
        self._pending_export_batches: List[Any] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main_container"):
            # Coluna Esquerda: Árvore Hierárquica
            with Vertical(id="left_column"):
                yield Label("📂 [bold cyan]Explorador OneNote[/bold cyan] (h/j/k/l, Espaço=Marcar)", id="tree_title")
                yield LoadingIndicator(id="tree_loading")
                yield TreeBrowser(id="tree_browser")

            # Coluna Direita: Detalhes, Controles e Progresso
            with Vertical(id="right_column"):
                with Vertical(id="details_card"):
                    yield Label("📋 Informações do Item", id="card_title")
                    yield Static("Nenhum item selecionado.", id="details_content")

                with Vertical(id="actions_card"):
                    yield Label("⚙ Opções & Ações de Exportação", classes="card_title")
                    with Horizontal():
                        yield Label("Pasta de Saída: ", classes="detail_row")
                        yield Input(value=str(DEFAULT_EXPORT_DIR), id="input_output_dir")
                    with Horizontal():
                        yield Label("Delay HTTP (ms): ", classes="detail_row")
                        yield Input(value=str(DEFAULT_REQUEST_DELAY_MS), id="input_delay_ms")
                    with Horizontal(id="actions_row"):
                        yield Button("Exportar Selecionados (e)", id="btn_export", variant="success")
                        yield Button("Recarregar (r)", id="btn_refresh", variant="default")
                        yield Button("Login/Conta (L)", id="btn_login", variant="primary")

                with Container(id="progress_container"):
                    yield ProgressPanel(id="progress_panel")

        yield Footer()

    def on_mount(self) -> None:
        """Called when screen is mounted."""
        tree = self.query_one("#tree_browser", TreeBrowser)
        tree.focus()

        if not self.api.is_authenticated():
            self.action_open_login()
        else:
            self.action_refresh_tree()

    def action_open_login(self) -> None:
        """Open login modal."""
        def on_login_closed(authenticated: Optional[bool]):
            if authenticated:
                self.action_refresh_tree()

        self.app.push_screen(LoginModal(self.api), on_login_closed)

    def action_refresh_tree(self) -> None:
        """Reload notebooks into tree."""
        self._load_notebooks()

    def action_export_selected(self) -> None:
        """Trigger export of all checked items."""
        if self.is_exporting:
            self.notify("Já existe uma exportação em andamento!", severity="warning")
            return

        tree = self.query_one("#tree_browser", TreeBrowser)
        selected_nodes = tree.get_selected_targets()

        if not selected_nodes:
            # Fallback to cursor node if user didn't check anything
            if (
                tree.cursor_node
                and tree.cursor_node.data
                and tree.cursor_node.data.node_type in ("notebook", "section_group", "section", "page")
            ):
                selected_nodes = [tree.cursor_node.data]
            else:
                self.notify("Nenhum item selecionado. Use [Espaço] para marcar itens.", severity="warning")
                return

        out_dir_val = self.query_one("#input_output_dir", Input).value.strip() or str(DEFAULT_EXPORT_DIR)
        delay_val_str = self.query_one("#input_delay_ms", Input).value.strip() or str(DEFAULT_REQUEST_DELAY_MS)
        try:
            delay_ms = int(delay_val_str)
        except ValueError:
            delay_ms = DEFAULT_REQUEST_DELAY_MS

        with self._export_lock:
            if self.is_exporting:
                self._pending_export_batches.append((selected_nodes, Path(out_dir_val), delay_ms))
                self.notify(
                    f"Itens adicionados à fila de exportação (+{len(selected_nodes)} item(ns))!",
                    title="Fila de Tarefas",
                    severity="information",
                    timeout=3.5,
                )
                return

            self.is_exporting = True
            btn_export = self.query_one("#btn_export", Button)
            btn_export.disabled = True
            btn_export.label = "⏳ Exportando..."
            self.notify(
                "⏳ Exportação iniciada! Levantando tarefas a executar...",
                title="Exportação em Andamento",
                severity="information",
                timeout=3.5,
            )

            progress = self.query_one("#progress_panel", ProgressPanel)
            progress.prepare_job("Levantando lista de páginas no OneNote...")

            self._run_export_job(selected_nodes, Path(out_dir_val), delay_ms)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks."""
        bid = event.button.id
        if bid == "btn_export":
            self.action_export_selected()
        elif bid == "btn_refresh":
            self.action_refresh_tree()
        elif bid == "btn_login":
            self.action_open_login()

    @on(TreeBrowser.NodeSelectionChanged)
    def handle_selection_changed(self, event: TreeBrowser.NodeSelectionChanged) -> None:
        """Update details panel when cursor moves or items are checked."""
        details_box = self.query_one("#details_content", Static)
        curr = event.current_node
        if curr is None or curr.data is None or curr.data.node_type == "root":
            details_box.update("Nenhum item em foco.")
            return

        data = curr.data
        if data.node_type == "loading":
            details_box.update(
                f"[bold yellow]⏳ {data.name}[/bold yellow]\n\n"
                "[dim]Aguarde a resposta do Microsoft OneNote...[/dim]"
            )
            return

        type_names = {
            "notebook": "Caderno",
            "section_group": "Grupo de Seções",
            "section": "Seção",
            "page": "Página",
            "empty": "Vazio",
            "error": "Erro",
        }
        tipo = type_names.get(data.node_type, data.node_type.title())

        lines = [
            f"[bold cyan]Tipo:[/bold cyan] {tipo}",
            f"[bold cyan]Nome:[/bold cyan] {data.name}",
            f"[bold cyan]ID:[/bold cyan] [dim]{data.id}[/dim]",
        ]

        if data.parent_notebook_name:
            lines.append(f"[bold cyan]Caderno:[/bold cyan] {data.parent_notebook_name}")
        if data.parent_section_name:
            lines.append(f"[bold cyan]Seção:[/bold cyan] {data.parent_section_name}")
        if data.parent_path:
            lines.append(f"[bold cyan]Hierarquia:[/bold cyan] {data.parent_path}")

        if data.loading:
            lines.append("[bold cyan]Status:[/bold cyan] [bold yellow]⏳ Buscando dados no Microsoft OneNote...[/bold yellow]")
        else:
            status_checked = "[green]Marcado para exportação [x][/green]" if data.checked else "[dim]Não marcado [ ][/dim]"
            lines.append(f"[bold cyan]Status:[/bold cyan] {status_checked}")

        lines.append(f"[bold yellow]Total de itens marcados:[/bold yellow] {event.selected_count}")

        details_box.update("\n".join(lines))

    def _call_on_ui_thread(self, callback: Any, *args: Any, **kwargs: Any) -> None:
        """Call a function safely on the Textual UI thread from worker or main thread."""
        import threading

        if getattr(self.app, "_thread_id", None) == threading.get_ident():
            callback(*args, **kwargs)
        else:
            self.app.call_from_thread(callback, *args, **kwargs)

    def show_error_modal(
        self,
        title: str,
        message: str,
        context: Optional[str] = None,
        exc: Optional[BaseException] = None,
    ) -> None:
        """Log structured error with timestamp to onebridge_tui_errors.log and show modal summary."""
        log_path = log_tui_error(context or title, exc=exc)

        def _open():
            self.app.push_screen(
                ErrorModal(
                    title=title,
                    message=message,
                    context=context,
                    log_path=str(log_path),
                )
            )

        self._call_on_ui_thread(_open)

    def _start_node_load(self, node: TreeNode[NodeData]) -> None:
        """Mark node loading synchronously on main thread and dispatch background worker."""
        if not node.data or node.data.loaded or node.data.loading:
            return

        tree = self.query_one("#tree_browser", TreeBrowser)
        tree_title = self.query_one("#tree_title", Label)

        messages = {
            "notebook": "Buscando seções e grupos no OneNote...",
            "section_group": "Buscando grupos e seções no OneNote...",
            "section": "Buscando páginas da seção...",
        }
        loading_msg = messages.get(node.data.node_type, "Carregando...")

        # 1. Synchronously mark as loading on main thread
        tree.set_node_loading(node, True, loading_msg)
        tree_title.update(
            f"📂 [bold cyan]Explorador OneNote[/bold cyan] [bold yellow]⏳ ⠋ {loading_msg}[/bold yellow]"
        )

        # 2. Dispatch background worker thread
        self._load_node_children(node)

    @on(TreeBrowser.NodeExpansionRequested)
    def handle_node_expansion_requested(self, event: TreeBrowser.NodeExpansionRequested) -> None:
        """Lazy-load children for an expanded node."""
        self._start_node_load(event.node)

    @on(Tree.NodeExpanded)
    def handle_tree_node_expanded(self, event: Tree.NodeExpanded) -> None:
        """Handle tree node expansion triggered directly by Textual (e.g. mouse click or Enter)."""
        node = event.node
        if (
            node.data
            and not node.data.loaded
            and not node.data.loading
            and node.data.node_type in ("notebook", "section_group", "section")
        ):
            self._start_node_load(node)

    @work(thread=True)
    def _load_notebooks(self) -> None:
        """Fetch all notebooks from API and populate tree."""
        def _show_loading(show: bool):
            self.query_one("#tree_loading", LoadingIndicator).display = show
            tree_title = self.query_one("#tree_title", Label)
            if show:
                tree_title.update(
                    "📂 [bold cyan]Explorador OneNote[/bold cyan] [bold yellow]⏳ ⠋ Buscando cadernos no OneNote...[/bold yellow]"
                )
            else:
                tree_title.update("📂 [bold cyan]Explorador OneNote[/bold cyan] (h/j/k/l, Espaço=Marcar)")

        self.app.call_from_thread(_show_loading, True)
        tree = self.query_one("#tree_browser", TreeBrowser)

        try:
            notebooks = self.api.list_notebooks(sort_by="name", reverse=False)

            def _populate():
                tree.clear()
                for nb in notebooks:
                    tree.add_notebook_node(nb)
                if len(tree.root.children) > 0:
                    tree.select_node(tree.root.children[0])

            self.app.call_from_thread(_populate)
        except Exception as exc:
            def _handle_notebooks_error():
                self.show_error_modal(
                    title="Falha ao Listar Cadernos",
                    message=str(exc),
                    context="Carregamento inicial de cadernos no OneNote",
                    exc=exc,
                )

            self._call_on_ui_thread(_handle_notebooks_error)
        finally:
            self.app.call_from_thread(_show_loading, False)

    @work(thread=True)
    def _load_node_children(self, node: TreeNode[NodeData]) -> None:
        """Fetch child sections/pages for a node."""
        if not node.data:
            return

        data = node.data
        tree = self.query_one("#tree_browser", TreeBrowser)
        tree_title = self.query_one("#tree_title", Label)

        try:
            if data.node_type == "notebook":
                nb_tree = self.api.get_notebook_tree(data.id)

                def _add_sections():
                    tree.set_node_loading(node, False)
                    # 1. Add direct section groups
                    for sg in nb_tree.section_groups:
                        tree.add_section_group_node(
                            node,
                            sg,
                            notebook_id=data.id,
                            notebook_name=data.name,
                            parent_path=sg.parent_path,
                        )
                    # 2. Add direct sections
                    for sec in nb_tree.sections:
                        tree.add_section_node(
                            node,
                            sec,
                            notebook_id=data.id,
                            notebook_name=data.name,
                            parent_path="",
                        )
                    if len(nb_tree.section_groups) == 0 and len(nb_tree.sections) == 0:
                        empty_data = NodeData(
                            node_type="empty",
                            id=f"empty-{data.id}",
                            name="(Nenhuma seção encontrada)",
                            loaded=True,
                        )
                        node.add_leaf(
                            label=tree.format_node_label(empty_data),
                            data=empty_data,
                        )
                    data.loaded = True

                self.app.call_from_thread(_add_sections)

            elif data.node_type == "section_group":
                parent_prefix = f"{data.parent_path}/{data.name}" if data.parent_path else data.name
                sections = self.api.list_section_group_sections(data.id, parent_path=parent_prefix)
                groups = self.api.list_section_group_section_groups(data.id, parent_path=parent_prefix)

                def _add_group_children():
                    tree.set_node_loading(node, False)
                    for g in groups:
                        tree.add_section_group_node(
                            node,
                            g,
                            notebook_id=data.parent_notebook_id or "",
                            notebook_name=data.parent_notebook_name or "",
                            parent_path=parent_prefix,
                        )
                    for s in sections:
                        tree.add_section_node(
                            node,
                            s,
                            notebook_id=data.parent_notebook_id or "",
                            notebook_name=data.parent_notebook_name or "",
                            parent_path=parent_prefix,
                        )
                    if len(groups) == 0 and len(sections) == 0:
                        empty_data = NodeData(
                            node_type="empty",
                            id=f"empty-{data.id}",
                            name="(Vazio)",
                            loaded=True,
                        )
                        node.add_leaf(
                            label=tree.format_node_label(empty_data),
                            data=empty_data,
                        )
                    data.loaded = True

                self.app.call_from_thread(_add_group_children)

            elif data.node_type == "section":
                pages = self.api.list_pages(section=data.id, notebook=data.parent_notebook_id)

                def _add_pages():
                    tree.set_node_loading(node, False)
                    for page in pages:
                        tree.add_page_node(
                            node,
                            page,
                            notebook_id=data.parent_notebook_id or "",
                            notebook_name=data.parent_notebook_name or "",
                            section_id=data.id,
                            section_name=data.name,
                            parent_path=data.parent_path,
                        )
                    if len(pages) == 0:
                        empty_data = NodeData(
                            node_type="empty",
                            id=f"empty-{data.id}",
                            name="(Nenhuma página encontrada)",
                            loaded=True,
                        )
                        node.add_leaf(
                            label=tree.format_node_label(empty_data),
                            data=empty_data,
                        )
                    data.loaded = True

                self.app.call_from_thread(_add_pages)

        except Exception as exc:
            def _handle_error():
                tree.set_node_loading(node, False)
                err_data = NodeData(
                    node_type="error",
                    id=f"err-{data.id}",
                    name=f"Erro ao carregar: {exc}",
                    loaded=False,
                )
                node.add_leaf(
                    label=tree.format_node_label(err_data),
                    data=err_data,
                )
                self.show_error_modal(
                    title="Falha ao Carregar Itens",
                    message=str(exc),
                    context=f"Buscando itens de '{data.name}' ({data.node_type})",
                    exc=exc,
                )

            self._call_on_ui_thread(_handle_error)
        finally:
            def _reset_title():
                if not tree.has_loading_nodes:
                    tree_title.update("📂 [bold cyan]Explorador OneNote[/bold cyan] (h/j/k/l, Espaço=Marcar)")
            self.app.call_from_thread(_reset_title)

    def _resolve_targets_to_pages(
        self, selected_targets: List[NodeData], progress: ProgressPanel
    ) -> List[PageDTO]:
        """Resolve tree node targets to concrete PageDTO list."""
        resolved_pages: Dict[str, PageDTO] = {}

        for item in selected_targets:
            if item.node_type == "page" and item.dto:
                resolved_pages[item.id] = item.dto
            elif item.node_type == "section":
                self.app.call_from_thread(
                    progress.set_status_text, f"Buscando páginas da seção '{item.name}'..."
                )
                pages = self.api.list_pages(section=item.id, notebook=item.parent_notebook_id)
                for p in pages:
                    resolved_pages[p.id] = p
            elif item.node_type == "notebook":
                self.app.call_from_thread(
                    progress.set_status_text, f"Buscando seções do caderno '{item.name}'..."
                )
                sections = self.api.list_sections(notebook=item.id, recursive=True)
                for s in sections:
                    self.app.call_from_thread(
                        progress.set_status_text, f"Buscando páginas de '{s.name}'..."
                    )
                    try:
                        pages = self.api.list_pages(section=s.id, notebook=item.id)
                        for p in pages:
                            resolved_pages[p.id] = p
                    except Exception:
                        pass
            elif item.node_type == "section_group":
                self.app.call_from_thread(
                    progress.set_status_text, f"Buscando grupo de seções '{item.name}'..."
                )
                sections = self.api.list_sections_in_section_group(item.id, recursive=True)
                for sec_dto in sections:
                    self.app.call_from_thread(
                        progress.set_status_text, f"Buscando páginas de '{sec_dto.name}'..."
                    )
                    try:
                        pages = self.api.list_pages(section=sec_dto.id, notebook=item.parent_notebook_id)
                        for p in pages:
                            resolved_pages[p.id] = p
                    except Exception:
                        pass

        return list(resolved_pages.values())

    @work(thread=True)
    def _run_export_job(
        self, selected_targets: List[NodeData], output_dir: Path, delay_ms: int
    ) -> None:
        """Resolve all pages under selected items and export them sequentially, draining queue."""
        import time

        start_time = time.time()
        self.is_exporting = True
        progress = self.query_one("#progress_panel", ProgressPanel)
        btn_export = self.query_one("#btn_export", Button)

        def _set_btn_exporting(label: str = "⏳ Exportando..."):
            btn_export.disabled = True
            btn_export.label = label

        self.app.call_from_thread(_set_btn_exporting)

        try:
            current_targets = selected_targets
            current_out_dir = output_dir
            current_delay = delay_ms
            all_tasks_processed: List[ExportTask] = []
            is_first_batch = True

            while True:
                pages_list = self._resolve_targets_to_pages(current_targets, progress)
                batch_tasks = [
                    ExportTask(
                        id=f"task-{p.id}",
                        page_id=p.id,
                        title=p.title,
                        notebook_name=getattr(p, "parent_notebook_name", "") or "",
                        section_name=getattr(p, "parent_section_name", "") or "",
                        output_dir=str(current_out_dir),
                    )
                    for p in pages_list
                ]

                if is_first_batch:
                    if len(batch_tasks) == 0 and not self._pending_export_batches:
                        self.app.call_from_thread(
                            progress.finish_job, False, "Nenhuma página encontrada nos itens selecionados."
                        )
                        self.app.call_from_thread(
                            self.notify, "Nenhuma página encontrada para exportar.", severity="warning"
                        )
                        return
                    self.app.call_from_thread(progress.set_tasks, batch_tasks)
                    self.app.call_from_thread(progress.start_job, len(batch_tasks), "Exportando Tarefas")
                    is_first_batch = False
                else:
                    self.app.call_from_thread(progress.add_tasks, batch_tasks)

                all_tasks_processed.extend(batch_tasks)

                # Process batch tasks
                for idx, task in enumerate(batch_tasks, start=1):
                    total_so_far = progress.total_pages or len(all_tasks_processed)
                    completed_so_far = progress.exported_pages + progress.failed_pages + 1

                    def _update_btn_progress(current=completed_so_far, total_pages=total_so_far):
                        btn_export.label = f"⏳ Exportando ({current}/{total_pages})..."

                    self.app.call_from_thread(_update_btn_progress)
                    self.app.call_from_thread(progress.start_task, task.id)

                    try:
                        result = self.api.fetch_page(
                            page=task.page_id,
                            output_dir=Path(task.output_dir),
                            overwrite=True,
                            delay_ms=current_delay,
                        )
                        images_count = getattr(result, "images_downloaded", getattr(result, "images_count", 0))
                        attachments_count = getattr(result, "attachments_downloaded", getattr(result, "attachments_count", 0))
                        file_path = getattr(result, "relative_path", getattr(result, "file_path", ""))
                        self.app.call_from_thread(
                            progress.complete_task,
                            task_id=task.id,
                            images_count=images_count,
                            attachments_count=attachments_count,
                            file_path=file_path,
                        )
                    except Exception as exc:
                        logger.error(f"Erro ao exportar página '{task.title}': {exc}", exc_info=True)
                        self.app.call_from_thread(
                            progress.fail_task,
                            task_id=task.id,
                            error_msg=str(exc),
                        )

                # Check if new batches were enqueued
                with self._export_lock:
                    if self._pending_export_batches:
                        next_batch = self._pending_export_batches.pop(0)
                        current_targets, current_out_dir, current_delay = next_batch
                    else:
                        break

            # Export finished!
            duration = time.time() - start_time
            pages_exported = progress.exported_pages
            images_exported = progress.total_images
            attachments_exported = progress.total_attachments
            failed_count = progress.failed_pages
            total_processed = progress.total_pages or len(all_tasks_processed)

            self.app.call_from_thread(
                progress.finish_job,
                True,
                f"Exportação finalizada! {pages_exported} de {total_processed} tarefa(s) concluída(s).",
            )
            self.app.call_from_thread(
                self.notify,
                f"Exportação concluída! {pages_exported} tarefa(s) exportadas.",
                title="Exportação Finalizada",
                severity="information",
                timeout=5.0,
            )

            try:
                self.app.call_from_thread(self.app.bell)
            except Exception:
                pass

            def _open_complete_modal():
                self.app.push_screen(
                    ExportCompleteModal(
                        total_pages=total_processed,
                        exported_pages=pages_exported,
                        total_images=images_exported,
                        total_attachments=attachments_exported,
                        failed_pages=failed_count,
                        output_dir=str(output_dir),
                        duration_seconds=duration,
                    )
                )

            self._call_on_ui_thread(_open_complete_modal)

        except Exception as exc:
            def _handle_export_error():
                progress.finish_job(False, f"Erro: {exc}")
                self.show_error_modal(
                    title="Falha na Exportação",
                    message=str(exc),
                    context="Processamento do lote de exportação",
                    exc=exc,
                )

            self._call_on_ui_thread(_handle_export_error)
        finally:
            with self._export_lock:
                self.is_exporting = False
                self._pending_export_batches.clear()

            def _reset_btn():
                btn_export.disabled = False
                btn_export.label = "Exportar Selecionados (e)"

            self.app.call_from_thread(_reset_btn)
