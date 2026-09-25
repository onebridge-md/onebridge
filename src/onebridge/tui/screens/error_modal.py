"""Modal dialog for displaying friendly error summaries in OneBridge TUI."""

from pathlib import Path
from typing import Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static

from onebridge.config import TUI_ERROR_LOG_PATH


class ErrorModal(ModalScreen[None]):
    """Modal dialog displaying error summary and details without breaking the TUI."""

    BINDINGS = [
        Binding("escape", "dismiss", "Fechar (Esc)"),
        Binding("enter", "dismiss", "Fechar (Enter)"),
        Binding("space", "dismiss", "Fechar (Espaço)"),
    ]

    DEFAULT_CSS = """
    ErrorModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.75);
    }

    #error_dialog {
        width: 76;
        height: auto;
        max-height: 85%;
        background: $surface;
        border: thick $error;
        padding: 1 2;
    }

    #error_title {
        text-style: bold;
        color: $error;
        text-align: center;
        margin-bottom: 1;
    }

    #error_context {
        text-style: bold;
        color: $text;
        margin-bottom: 1;
    }

    #error_scroll_box {
        max-height: 12;
        background: $panel;
        border: round $error-muted;
        padding: 1;
        margin-bottom: 1;
    }

    #error_summary {
        color: $text;
    }

    #error_log_notice {
        color: $text-muted;
        margin-bottom: 1;
        text-align: center;
    }

    #buttons_row {
        height: auto;
        align: center middle;
        margin-top: 1;
    }

    #buttons_row Button {
        min-width: 22;
    }
    """

    def __init__(
        self,
        title: str = "Falha na Operação",
        message: str = "Ocorreu um erro inesperado.",
        context: Optional[str] = None,
        log_path: Optional[str] = None,
    ):
        super().__init__()
        self.error_title = title
        self.error_message = message
        self.error_context = context
        self.error_log_path = log_path or str(TUI_ERROR_LOG_PATH)

    def compose(self) -> ComposeResult:
        with Vertical(id="error_dialog"):
            yield Label(f"⚠️  {self.error_title}", id="error_title")
            if self.error_context:
                yield Label(f"[bold cyan]Operação:[/bold cyan] {self.error_context}", id="error_context")
            with VerticalScroll(id="error_scroll_box"):
                yield Static(self._format_message(), id="error_summary")
            yield Static(
                f"[dim]📁 Detalhes técnicos e stack trace registrados em:[/dim]\n"
                f"[bold cyan]{self.error_log_path}[/bold cyan]",
                id="error_log_notice",
            )
            with Horizontal(id="buttons_row"):
                yield Button("Fechar (Enter / Esc)", id="btn_close", variant="error")

    def _format_message(self) -> Text:
        """Format the error message cleanly for the user."""
        text = Text()
        text.append("Resumo do Erro:\n", style="bold yellow")
        text.append(f"{self.error_message}\n", style="white")
        return text

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button click."""
        if event.button.id == "btn_close":
            self.dismiss()
