"""Main Textual application for OneBridge TUI."""

from typing import Optional

from textual import on
from textual.app import App
from textual.binding import Binding
from textual.worker import Worker, WorkerState

from onebridge import __version__
from onebridge.api.client import OneBridgeAPI
from onebridge.logger import (
    TUIStderrCapture,
    enable_stderr_logging,
    log_tui_error,
    setup_logging,
)
from onebridge.tui.screens.error_modal import ErrorModal
from onebridge.tui.screens.main import MainScreen


class OneBridgeTUIApp(App):
    """Interactive TUI for browsing and exporting Microsoft OneNote notebooks."""

    TITLE = "OneBridge"
    SUB_TITLE = "OneNote to Markdown Exporter"

    BINDINGS = [
        Binding("ctrl+c", "quit", "Sair", priority=True),
    ]

    CSS = """
    Screen {
        background: $background;
        color: $text;
    }

    Header {
        background: $primary-background;
        color: $primary-lighten-2;
    }

    Footer {
        background: $primary-background;
    }
    """

    def __init__(self, api: Optional[OneBridgeAPI] = None):
        super().__init__()
        # In TUI mode, disable stderr logging to avoid screen corruption
        setup_logging(force=True, enable_stderr=False)
        enable_stderr_logging(False)
        self.api = api or OneBridgeAPI()

    def on_mount(self) -> None:
        """Mount main screen on startup."""
        self.push_screen(MainScreen(self.api))

    @on(Worker.StateChanged)
    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Catch any uncaught worker error, log to onebridge_tui_errors.log and show modal."""
        if event.state == WorkerState.ERROR and event.worker.error:
            exc = event.worker.error
            log_path = log_tui_error(
                context="Exceção não tratada em worker em segundo plano",
                exc=exc,
            )
            if not isinstance(self.screen, ErrorModal):
                self.push_screen(
                    ErrorModal(
                        title="Erro Inesperado na TUI",
                        message=str(exc),
                        context="Worker em segundo plano",
                        log_path=str(log_path),
                    )
                )


def run_tui(api: Optional[OneBridgeAPI] = None) -> None:
    """Convenience entrypoint to execute the TUI app with stderr capture."""
    setup_logging(force=True, enable_stderr=False)
    enable_stderr_logging(False)
    app = OneBridgeTUIApp(api=api)
    try:
        with TUIStderrCapture():
            app.run()
    finally:
        # Re-enable stderr logging after exiting TUI
        enable_stderr_logging(True)


if __name__ == "__main__":
    run_tui()
