"""Modal dialog displaying export completion summary in OneBridge TUI."""

from pathlib import Path
from typing import Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


class ExportCompleteModal(ModalScreen[None]):
    """Modal dialog displaying successful completion summary of an export job."""

    BINDINGS = [
        Binding("escape", "dismiss", "Fechar (Esc)"),
        Binding("enter", "dismiss", "Fechar (Enter)"),
        Binding("space", "dismiss", "Fechar (Espaço)"),
    ]

    DEFAULT_CSS = """
    ExportCompleteModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.75);
    }

    #export_dialog {
        width: 72;
        height: auto;
        max-height: 85%;
        background: $surface;
        border: thick $success;
        padding: 1 2;
    }

    #export_title {
        text-style: bold;
        color: $success;
        text-align: center;
        margin-bottom: 1;
    }

    #export_subtitle {
        text-align: center;
        color: $text;
        margin-bottom: 1;
    }

    #summary_card {
        background: $panel;
        border: round $success-muted;
        padding: 1 2;
        margin-bottom: 1;
        height: auto;
    }

    #export_dir_notice {
        color: $text-muted;
        text-align: center;
        margin-bottom: 1;
    }

    #buttons_row {
        height: auto;
        align: center middle;
        margin-top: 1;
    }

    #buttons_row Button {
        min-width: 24;
    }
    """

    def __init__(
        self,
        total_pages: int,
        exported_pages: int,
        total_images: int = 0,
        total_attachments: int = 0,
        failed_pages: int = 0,
        output_dir: str = "",
        duration_seconds: Optional[float] = None,
    ):
        super().__init__()
        self.total_pages = total_pages
        self.exported_pages = exported_pages
        self.total_images = total_images
        self.total_attachments = total_attachments
        self.failed_pages = failed_pages
        self.output_dir = output_dir
        self.duration_seconds = duration_seconds

    def compose(self) -> ComposeResult:
        with Vertical(id="export_dialog"):
            yield Label("🎉 Exportação Concluída!", id="export_title")
            yield Label(
                "A solicitação de exportação foi finalizada com sucesso.",
                id="export_subtitle",
            )
            with Vertical(id="summary_card"):
                yield Static(self._format_summary(), id="export_stats")

            if self.output_dir:
                yield Static(
                    f"[dim]📁 Destino dos arquivos:[/dim]\n[bold cyan]{self.output_dir}[/bold cyan]",
                    id="export_dir_notice",
                )

            with Horizontal(id="buttons_row"):
                yield Button("Concluir (Enter / Esc)", id="btn_close", variant="success")

    def _format_summary(self) -> Text:
        """Format the summary statistics cleanly."""
        text = Text()
        text.append("📄 Páginas exportadas: ", style="bold cyan")
        text.append(f"{self.exported_pages} de {self.total_pages}\n", style="bold white")

        text.append("🖼️  Imagens extraídas:  ", style="bold cyan")
        text.append(f"{self.total_images}\n", style="white")

        text.append("📎 Anexos baixados:   ", style="bold cyan")
        text.append(f"{self.total_attachments}\n", style="white")

        if self.failed_pages > 0:
            text.append("⚠️  Páginas com falha:  ", style="bold red")
            text.append(f"{self.failed_pages}\n", style="bold red")

        if self.duration_seconds is not None:
            text.append("⏱️  Tempo total:        ", style="bold cyan")
            text.append(f"{self.duration_seconds:.1f}s\n", style="white")

        return text

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button click."""
        if event.button.id == "btn_close":
            self.dismiss()
