"""ProgressPanel widget with progress bar, metrics, live task list, and log stream."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.timer import Timer
from textual.widgets import (
    DataTable,
    Label,
    ProgressBar,
    RichLog,
    Static,
    TabbedContent,
    TabPane,
)


@dataclass
class ExportTask:
    """Represents a single OneNote page export task with live status."""

    id: str
    page_id: str
    title: str
    notebook_name: str = ""
    section_name: str = ""
    output_dir: str = ""
    status: str = "queued"  # "queued", "running", "completed", "failed"
    details: str = "Aguardando na fila..."
    images_count: int = 0
    attachments_count: int = 0
    file_path: Optional[str] = None
    error_message: Optional[str] = None


class ProgressPanel(Container):
    """Panel displaying real-time export progress, active tasks list, counters, and log stream."""

    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    DEFAULT_CSS = """
    ProgressPanel {
        height: 100%;
        background: $surface;
        border: solid $accent;
        padding: 1;
    }

    #panel_title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    #progress_status {
        color: $text;
        margin-bottom: 1;
    }

    #progress_bar {
        width: 100%;
        margin-bottom: 1;
    }

    #metrics_bar {
        height: auto;
        margin-bottom: 1;
        background: $boost;
        padding: 0 1;
    }

    .metric_badge {
        margin-right: 2;
        color: $text-muted;
    }

    #progress_tabs {
        height: 1fr;
    }

    #progress_tabs TabPane {
        padding: 0;
        height: 1fr;
    }

    #tasks_table {
        height: 1fr;
        background: $panel;
        border: round $primary-background;
    }

    #tasks_table > .datatable--header {
        text-style: bold;
        color: $accent;
        background: $boost;
    }

    #tasks_table > .datatable--cursor {
        background: $primary 30%;
    }

    #log_stream {
        height: 1fr;
        background: $panel;
        border: round $primary-background;
    }
    """

    def __init__(
        self,
        *,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ):
        super().__init__(name=name, id=id, classes=classes)
        self.total_pages = 0
        self.exported_pages = 0
        self.total_images = 0
        self.total_attachments = 0
        self.failed_pages = 0
        self._spinner_frame = 0
        self._spinner_timer: Optional[Timer] = None
        self._current_task_text = "Aguardando início de tarefas..."
        self.tasks: Dict[str, ExportTask] = {}
        self._active_task_id: Optional[str] = None
        self._col_status = None
        self._col_task = None
        self._col_origin = None
        self._col_details = None

    def compose(self) -> ComposeResult:
        yield Label("📊 Progresso e Tarefas de Exportação", id="panel_title")
        yield Label("Aguardando início de tarefas...", id="progress_status")
        yield ProgressBar(id="progress_bar", show_eta=False, total=100)
        with Horizontal(id="metrics_bar"):
            yield Static("Páginas: 0/0", id="metric_pages", classes="metric_badge")
            yield Static("Imagens: 0", id="metric_images", classes="metric_badge")
            yield Static("Anexos: 0", id="metric_attachments", classes="metric_badge")
        with TabbedContent(id="progress_tabs", initial="tab_tasks"):
            with TabPane("📋 Tarefas (0)", id="tab_tasks"):
                yield DataTable(id="tasks_table", zebra_stripes=True)
            with TabPane("📜 Log Detalhado", id="tab_logs"):
                yield RichLog(id="log_stream", highlight=True, markup=True, wrap=True, auto_scroll=True)

    def on_mount(self) -> None:
        """Initialize columns in DataTable on mount."""
        self._ensure_columns()

    def _ensure_columns(self) -> None:
        """Ensure columns exist in DataTable."""
        try:
            dt = self.query_one("#tasks_table", DataTable)
            dt.cursor_type = "row"
            if not dt.columns:
                cols = dt.add_columns("Status", "Tarefa / Página", "Origem", "Progresso / Detalhes")
                self._col_status, self._col_task, self._col_origin, self._col_details = cols
        except Exception:
            pass

    def _format_status(self, status: str, frame: str = "") -> Text:
        """Format status indicator with color and icons."""
        if status == "running":
            spinner_char = frame or self.SPINNER_FRAMES[self._spinner_frame]
            return Text(f"⏳ {spinner_char} Ativa", style="bold cyan")
        elif status == "completed":
            return Text("✔ Concluído", style="bold green")
        elif status == "failed":
            return Text("✖ Falha", style="bold red")
        else:  # queued
            return Text("⏳ Na fila", style="yellow")

    def _update_tab_title(self) -> None:
        """Update tab label to show task counts and active status."""
        try:
            tabs = self.query_one("#progress_tabs", TabbedContent)
            tab = tabs.get_tab("tab_tasks")
            total = len(self.tasks)
            active = sum(1 for t in self.tasks.values() if t.status in ("queued", "running"))
            if active > 0:
                tab.label = f"📋 Tarefas ({total} | ⏳ {active})"
            elif total > 0:
                tab.label = f"📋 Tarefas ({total} ✔)"
            else:
                tab.label = "📋 Tarefas (0)"
        except Exception:
            pass

    def _start_spinner(self) -> None:
        """Start spinner animation timer if not already running."""
        if self._spinner_timer is None:
            try:
                self._spinner_timer = self.set_interval(0.1, self._tick_spinner)
            except Exception:
                self._spinner_timer = None

    def _stop_spinner(self) -> None:
        """Stop spinner animation timer."""
        if self._spinner_timer is not None:
            try:
                self._spinner_timer.stop()
            except Exception:
                pass
            self._spinner_timer = None

    def _tick_spinner(self) -> None:
        """Advance spinner animation frame and update status label + active task cell."""
        self._spinner_frame = (self._spinner_frame + 1) % len(self.SPINNER_FRAMES)
        frame = self.SPINNER_FRAMES[self._spinner_frame]
        try:
            status = self.query_one("#progress_status", Label)
            status.update(f"⏳ [bold yellow]{frame}[/bold yellow] {self._current_task_text}")
        except Exception:
            pass

        if self._active_task_id and self._col_status:
            try:
                dt = self.query_one("#tasks_table", DataTable)
                if self._active_task_id in dt.rows:
                    dt.update_cell(
                        self._active_task_id,
                        self._col_status,
                        self._format_status("running", frame),
                    )
            except Exception:
                pass

    def prepare_job(self, message: str = "Coletando páginas no OneNote...") -> None:
        """Indicate that export job has started and is discovering pages (indeterminate state)."""
        self.total_pages = 0
        self.exported_pages = 0
        self.total_images = 0
        self.total_attachments = 0
        self.failed_pages = 0
        self._active_task_id = None
        self._current_task_text = message

        self._start_spinner()

        try:
            title = self.query_one("#panel_title", Label)
            title.update("📊 Progresso e Tarefas [bold yellow]⏳ EM EXECUÇÃO[/bold yellow]")
        except Exception:
            pass

        try:
            bar = self.query_one("#progress_bar", ProgressBar)
            bar.update(total=None)
        except Exception:
            pass

        try:
            status = self.query_one("#progress_status", Label)
            status.update(f"⏳ ⠋ {message}")
        except Exception:
            pass

        self._update_badges()
        self.log_message("[bold cyan]▶ Iniciando processo de exportação...[/bold cyan]")
        self.log_message(f"[bold yellow]⏳ {message}[/bold yellow]")

    def set_status_text(self, message: str) -> None:
        """Update live status message during page collection or traversal."""
        self._current_task_text = message
        frame = self.SPINNER_FRAMES[self._spinner_frame]
        try:
            status = self.query_one("#progress_status", Label)
            status.update(f"⏳ [bold yellow]{frame}[/bold yellow] {message}")
        except Exception:
            pass

    def set_tasks(self, tasks: List[ExportTask]) -> None:
        """Initialize and populate task table with a list of tasks."""
        self._ensure_columns()
        self.tasks.clear()
        self._active_task_id = None
        self.total_pages = len(tasks)
        self.exported_pages = 0
        self.failed_pages = 0
        self.total_images = 0
        self.total_attachments = 0

        try:
            dt = self.query_one("#tasks_table", DataTable)
            dt.clear()
            for task in tasks:
                self.tasks[task.id] = task
                origin = (
                    f"{task.notebook_name} / {task.section_name}"
                    if task.notebook_name
                    else task.section_name
                )
                dt.add_row(
                    self._format_status(task.status),
                    task.title,
                    origin or "-",
                    task.details,
                    key=task.id,
                )
        except Exception:
            pass

        try:
            bar = self.query_one("#progress_bar", ProgressBar)
            bar.update(total=len(tasks) if tasks else 1, progress=0)
        except Exception:
            pass

        self._update_badges()
        self._update_tab_title()

    def add_tasks(self, tasks: List[ExportTask]) -> None:
        """Append new tasks to the task table and queue."""
        self._ensure_columns()
        self.total_pages += len(tasks)

        try:
            dt = self.query_one("#tasks_table", DataTable)
            for task in tasks:
                self.tasks[task.id] = task
                origin = (
                    f"{task.notebook_name} / {task.section_name}"
                    if task.notebook_name
                    else task.section_name
                )
                dt.add_row(
                    self._format_status(task.status),
                    task.title,
                    origin or "-",
                    task.details,
                    key=task.id,
                )
        except Exception:
            pass

        try:
            bar = self.query_one("#progress_bar", ProgressBar)
            bar.update(total=self.total_pages if self.total_pages > 0 else 1)
        except Exception:
            pass

        self._update_badges()
        self._update_tab_title()
        self.log_message(f"[bold cyan]➕ Adicionadas {len(tasks)} nova(s) tarefa(s) à lista.[/bold cyan]")

    def start_task(self, task_id: str) -> None:
        """Mark a specific task as running and start active animation."""
        self._ensure_columns()
        self._active_task_id = task_id
        task = self.tasks.get(task_id)
        if task:
            task.status = "running"
            task.details = "Baixando página e mídias..."
            frame = self.SPINNER_FRAMES[self._spinner_frame]
            self._current_task_text = f"Exportando ({self.exported_pages + 1}/{self.total_pages}): {task.title}"

            try:
                dt = self.query_one("#tasks_table", DataTable)
                if self._col_status and self._col_details and task_id in dt.rows:
                    dt.update_cell(task_id, self._col_status, self._format_status("running", frame))
                    dt.update_cell(task_id, self._col_details, task.details)
            except Exception:
                pass

            try:
                status = self.query_one("#progress_status", Label)
                status.update(f"⏳ [bold yellow]{frame}[/bold yellow] {self._current_task_text}")
            except Exception:
                pass

        self._update_tab_title()

    def complete_task(
        self,
        task_id: str,
        images_count: int = 0,
        attachments_count: int = 0,
        file_path: str = "",
    ) -> None:
        """Mark a specific task as completed."""
        self._ensure_columns()
        if self._active_task_id == task_id:
            self._active_task_id = None

        self.exported_pages += 1
        self.total_images += images_count
        self.total_attachments += attachments_count

        task = self.tasks.get(task_id)
        details_list = []
        if images_count:
            details_list.append(f"{images_count} img")
        if attachments_count:
            details_list.append(f"{attachments_count} anexo(s)")
        details_str = f"✔ Concluído ({', '.join(details_list)})" if details_list else "✔ Concluído"

        if task:
            task.status = "completed"
            task.images_count = images_count
            task.attachments_count = attachments_count
            task.file_path = file_path
            task.details = details_str
            task_title = task.title
        else:
            task_title = task_id

        try:
            dt = self.query_one("#tasks_table", DataTable)
            if self._col_status and self._col_details and task_id in dt.rows:
                dt.update_cell(task_id, self._col_status, self._format_status("completed"))
                dt.update_cell(task_id, self._col_details, details_str)
            elif task_id not in dt.rows:
                dt.add_row(self._format_status("completed"), task_title, "-", details_str, key=task_id)
        except Exception:
            pass

        try:
            bar = self.query_one("#progress_bar", ProgressBar)
            bar.advance(1)
        except Exception:
            pass

        self._update_badges()
        self._update_tab_title()

        log_path_str = f" ➔ [dim]{file_path}[/dim]" if file_path else ""
        self.log_message(f"[green]✔[/green] Exportada: [bold]{task_title}[/bold] ({details_str}){log_path_str}")

    def fail_task(self, task_id: str, error_msg: str) -> None:
        """Mark a specific task as failed."""
        self._ensure_columns()
        if self._active_task_id == task_id:
            self._active_task_id = None

        self.failed_pages += 1
        task = self.tasks.get(task_id)
        task_title = task.title if task else task_id
        if task:
            task.status = "failed"
            task.error_message = error_msg
            task.details = f"✖ {error_msg}"

        try:
            dt = self.query_one("#tasks_table", DataTable)
            if self._col_status and self._col_details and task_id in dt.rows:
                dt.update_cell(task_id, self._col_status, self._format_status("failed"))
                dt.update_cell(task_id, self._col_details, f"✖ {error_msg}")
            elif task_id not in dt.rows:
                dt.add_row(self._format_status("failed"), task_title, "-", f"✖ {error_msg}", key=task_id)
        except Exception:
            pass

        try:
            bar = self.query_one("#progress_bar", ProgressBar)
            bar.advance(1)
        except Exception:
            pass

        self._update_badges()
        self._update_tab_title()
        self.log_message(f"[red]✖ Falha na tarefa '{task_title}': {error_msg}[/red]")

    def start_job(self, total: int, title: str = "Iniciando exportação...") -> None:
        """Initialize progress bar and metrics for a concrete page export job."""
        self.total_pages = total
        self.exported_pages = 0
        self.total_images = 0
        self.total_attachments = 0
        self.failed_pages = 0
        self._current_task_text = f"{title} ({total} página(s))"

        self._start_spinner()

        try:
            title_widget = self.query_one("#panel_title", Label)
            title_widget.update("📊 Progresso e Tarefas [bold yellow]⏳ EM EXECUÇÃO[/bold yellow]")
        except Exception:
            pass

        try:
            bar = self.query_one("#progress_bar", ProgressBar)
            bar.update(total=total if total > 0 else 1, progress=0)
        except Exception:
            pass

        frame = self.SPINNER_FRAMES[self._spinner_frame]
        try:
            status = self.query_one("#progress_status", Label)
            status.update(f"⏳ [bold yellow]{frame}[/bold yellow] {self._current_task_text}")
        except Exception:
            pass

        self._update_badges()
        self._update_tab_title()
        self.log_message(f"[bold cyan]▶ Iniciando exportação de {total} página(s)[/bold cyan]")

    def advance_page(
        self,
        page_title: str,
        images_count: int = 0,
        attachments_count: int = 0,
        file_path: str = "",
    ) -> None:
        """Advance progress by one completed page (supports direct and task-based calls)."""
        matching_task_id = None
        if (
            self._active_task_id
            and self.tasks.get(self._active_task_id, None)
            and self.tasks[self._active_task_id].title == page_title
        ):
            matching_task_id = self._active_task_id
        else:
            for tid, t in self.tasks.items():
                if t.title == page_title and t.status in ("queued", "running"):
                    matching_task_id = tid
                    break

        if matching_task_id:
            self.complete_task(matching_task_id, images_count, attachments_count, file_path)
        else:
            auto_id = f"auto-{self.exported_pages + 1}"
            self.complete_task(auto_id, images_count, attachments_count, file_path)

    def record_failure(self, page_title: str, error_msg: str) -> None:
        """Record a failed page export without stopping the entire batch."""
        matching_task_id = None
        if (
            self._active_task_id
            and self.tasks.get(self._active_task_id, None)
            and self.tasks[self._active_task_id].title == page_title
        ):
            matching_task_id = self._active_task_id
        else:
            for tid, t in self.tasks.items():
                if t.title == page_title and t.status in ("queued", "running"):
                    matching_task_id = tid
                    break

        if matching_task_id:
            self.fail_task(matching_task_id, error_msg)
        else:
            auto_id = f"err-{self.failed_pages + 1}"
            self.fail_task(auto_id, error_msg)

    def finish_job(self, success: bool = True, message: str = "Concluído com sucesso!") -> None:
        """Mark current job as finished."""
        self._stop_spinner()
        self._active_task_id = None
        self._current_task_text = message

        try:
            title_widget = self.query_one("#panel_title", Label)
            if success:
                title_widget.update("📊 Progresso e Tarefas [bold green]✔ CONCLUÍDO[/bold green]")
            else:
                title_widget.update("📊 Progresso e Tarefas [bold red]✖ INTERROMPIDO[/bold red]")
        except Exception:
            pass

        try:
            bar = self.query_one("#progress_bar", ProgressBar)
            target_total = self.total_pages or 1
            bar.update(total=target_total, progress=target_total)
        except Exception:
            pass

        try:
            status = self.query_one("#progress_status", Label)
            if success:
                status.update(f"✅ {message}")
            else:
                status.update(f"❌ {message}")
        except Exception:
            pass

        self._update_tab_title()

        if success:
            self.log_message(f"[bold green]✔ {message}[/bold green]")
        else:
            self.log_message(f"[bold red]✖ {message}[/bold red]")

    def log_message(self, message: str) -> None:
        """Write a styled message line to the log stream."""
        try:
            log_view = self.query_one("#log_stream", RichLog)
            log_view.write(message)
        except Exception:
            pass

    def _update_badges(self) -> None:
        """Update metrics labels."""
        try:
            p_badge = self.query_one("#metric_pages", Static)
            if self.failed_pages > 0:
                p_badge.update(
                    f"Páginas: {self.exported_pages}/{self.total_pages} ([red]{self.failed_pages} falha(s)[/red])"
                )
            else:
                p_badge.update(f"Páginas: {self.exported_pages}/{self.total_pages}")
        except Exception:
            pass

        try:
            i_badge = self.query_one("#metric_images", Static)
            i_badge.update(f"Imagens: {self.total_images}")
        except Exception:
            pass

        try:
            a_badge = self.query_one("#metric_attachments", Static)
            a_badge.update(f"Anexos: {self.total_attachments}")
        except Exception:
            pass
