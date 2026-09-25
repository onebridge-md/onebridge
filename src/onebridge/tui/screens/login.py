"""Login modal screen for authenticating with Microsoft Identity."""

from typing import Optional

from textual import work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, LoadingIndicator, Static

from onebridge.api.client import OneBridgeAPI
from onebridge.logger import get_logger

logger = get_logger("onebridge.tui.screens.login")


class LoginModal(ModalScreen[bool]):
    """Modal dialog for authenticating or viewing session details."""

    DEFAULT_CSS = """
    LoginModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #login_dialog {
        width: 75;
        height: auto;
        max-height: 90%;
        background: $surface;
        border: thick $primary;
        padding: 2;
    }

    #login_title {
        text-style: bold;
        color: $accent;
        text-align: center;
        margin-bottom: 1;
    }

    #status_message {
        margin-bottom: 1;
        text-align: center;
    }

    #auth_instructions {
        background: $panel;
        border: round $secondary;
        padding: 1;
        margin: 1 0;
        text-align: center;
        display: none;
    }

    #loading {
        display: none;
        height: 3;
        margin-bottom: 1;
    }

    #buttons_row {
        height: auto;
        align: center middle;
        margin-top: 1;
    }

    Button {
        margin: 0 1;
    }
    """

    def __init__(self, api: OneBridgeAPI):
        super().__init__()
        self.api = api
        self.is_logging_in = False

    def compose(self) -> ComposeResult:
        with Vertical(id="login_dialog"):
            yield Label("🔐 Autenticação Microsoft OneNote", id="login_title")
            yield Static("Verificando credenciais...", id="status_message")
            yield Static("", id="auth_instructions")
            yield LoadingIndicator(id="loading")
            with Horizontal(id="buttons_row"):
                yield Button("Entrar (Device Code)", id="btn_device_login", variant="primary")
                yield Button("Entrar (Navegador)", id="btn_browser_login")
                yield Button("Fechar", id="btn_close", variant="default")

    def on_mount(self) -> None:
        """Check current session status on mount."""
        self._refresh_status()

    def _refresh_status(self) -> None:
        status_lbl = self.query_one("#status_message", Static)
        btn_device = self.query_one("#btn_device_login", Button)
        btn_browser = self.query_one("#btn_browser_login", Button)
        btn_close = self.query_one("#btn_close", Button)

        if self.api.is_authenticated():
            try:
                profile = self.api.get_current_user_profile()
                name = profile.display_name or "Usuário"
                email = profile.email or ""
                status_lbl.update(f"[green]✔ Conectado como:[/green] [bold]{name}[/bold] ({email})")
                btn_device.label = "Reautenticar"
                btn_close.label = "Continuar"
            except Exception:
                status_lbl.update("[yellow]Sessão expirada. Autentique-se novamente.[/yellow]")
        else:
            status_lbl.update("[yellow]Nenhuma conta conectada. Por favor, autentique-se para continuar.[/yellow]")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "btn_close":
            self.dismiss(self.api.is_authenticated())
        elif button_id == "btn_device_login":
            self._start_device_login()
        elif button_id == "btn_browser_login":
            self._start_browser_login()

    def _set_ui_busy(self, busy: bool) -> None:
        self.is_logging_in = busy
        self.query_one("#loading", LoadingIndicator).display = busy
        self.query_one("#btn_device_login", Button).disabled = busy
        self.query_one("#btn_browser_login", Button).disabled = busy

    @work(thread=True)
    def _start_device_login(self) -> None:
        self.app.call_from_thread(self._set_ui_busy, True)
        instr_box = self.query_one("#auth_instructions", Static)

        def on_prompt(msg: str) -> None:
            def _update():
                instr_box.display = True
                instr_box.update(f"[bold cyan]{msg}[/bold cyan]")
            self.app.call_from_thread(_update)

        try:
            self.api.auth.login_device_flow(prompt_callback=on_prompt)
            self.app.call_from_thread(self.notify, "Login realizado com sucesso!", severity="information")
            self.app.call_from_thread(self._refresh_status)
            self.app.call_from_thread(self.dismiss, True)
        except Exception as exc:
            logger.error(f"Erro no login: {exc}", exc_info=True)
            self.app.call_from_thread(self.notify, f"Falha no login: {exc}", severity="error")
            self.app.call_from_thread(self._refresh_status)
        finally:
            self.app.call_from_thread(self._set_ui_busy, False)

    @work(thread=True)
    def _start_browser_login(self) -> None:
        self.app.call_from_thread(self._set_ui_busy, True)
        try:
            self.api.auth.login_interactive()
            self.app.call_from_thread(self.notify, "Login realizado com sucesso!", severity="information")
            self.app.call_from_thread(self._refresh_status)
            self.app.call_from_thread(self.dismiss, True)
        except Exception as exc:
            logger.error(f"Erro no login via navegador: {exc}", exc_info=True)
            self.app.call_from_thread(self.notify, f"Falha no login: {exc}", severity="error")
            self.app.call_from_thread(self._refresh_status)
        finally:
            self.app.call_from_thread(self._set_ui_busy, False)
