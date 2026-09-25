"""Logging infrastructure for OneBridge."""

import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Union

from onebridge.config import LOG_FILE_PATH, LOG_LEVEL, TUI_ERROR_LOG_PATH

VALID_LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "WARN": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

_LOGGING_INITIALIZED = False


class OneBridgeFormatter(logging.Formatter):
    """Custom formatter generating '[YYYY-MM-DD hh:mm:ss] - [modulo] - [mensagem]'."""

    DEFAULT_FORMAT = "[%(asctime)s] - [%(name)s] - [%(message)s]"
    DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

    def __init__(
        self,
        fmt: str = DEFAULT_FORMAT,
        datefmt: str = DEFAULT_DATE_FORMAT,
    ):
        super().__init__(fmt=fmt, datefmt=datefmt)


class StderrErrorFilter(logging.Filter):
    """Filter that allows only ERROR and higher severity records through."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= logging.ERROR


def get_log_level(level_name: Optional[str] = None) -> int:
    """Resolve log level string to logging level integer."""
    name = (level_name or LOG_LEVEL).strip().upper()
    return VALID_LOG_LEVELS.get(name, logging.INFO)


def setup_logging(
    log_level: Optional[str] = None,
    log_file_path: Optional[Union[str, Path]] = None,
    force: bool = False,
    enable_stderr: bool = True,
) -> logging.Logger:
    """Initialize and configure the OneBridge logging system.
    
    Creates the destination directory if it does not exist, attaches a FileHandler
    with the configured log level and format, and optionally attaches a StreamHandler
    to STDERR strictly for ERROR level logs.
    """
    global _LOGGING_INITIALIZED

    target_logger = logging.getLogger("onebridge")

    if _LOGGING_INITIALIZED and not force:
        return target_logger

    resolved_level = get_log_level(log_level)
    target_path = Path(log_file_path or LOG_FILE_PATH)

    # Ensure parent log directory exists
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    target_logger.setLevel(resolved_level)

    # Clear existing handlers if forcing re-initialization
    if force:
        for handler in list(target_logger.handlers):
            target_logger.removeHandler(handler)
            handler.close()

    if not target_logger.handlers:
        formatter = OneBridgeFormatter()

        # 1. File Handler (all logs matching resolved_level)
        try:
            file_handler = logging.FileHandler(target_path, encoding="utf-8")
            file_handler.setLevel(resolved_level)
            file_handler.setFormatter(formatter)
            target_logger.addHandler(file_handler)
        except OSError as e:
            if enable_stderr:
                sys.stderr.write(f"Failed to create log file at {target_path}: {e}\n")

        # 2. STDERR Stream Handler (strictly ERROR and higher, if enabled)
        if enable_stderr:
            stderr_handler = logging.StreamHandler(sys.stderr)
            stderr_handler.setLevel(logging.ERROR)
            stderr_handler.addFilter(StderrErrorFilter())
            stderr_handler.setFormatter(formatter)
            target_logger.addHandler(stderr_handler)

    _LOGGING_INITIALIZED = True
    return target_logger


def enable_stderr_logging(enable: bool = True) -> None:
    """Dynamically enable or disable the STDERR logging handler."""
    target_logger = logging.getLogger("onebridge")
    for handler in list(target_logger.handlers):
        if isinstance(handler, logging.StreamHandler) and getattr(handler, "stream", None) == sys.stderr:
            target_logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass

    if enable:
        formatter = OneBridgeFormatter()
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setLevel(logging.ERROR)
        stderr_handler.addFilter(StderrErrorFilter())
        stderr_handler.setFormatter(formatter)
        target_logger.addHandler(stderr_handler)


def log_tui_error(
    context: str,
    exc: Optional[BaseException] = None,
    log_path: Optional[Union[str, Path]] = None,
    extra_info: Optional[Dict[str, Any]] = None,
) -> Path:
    """Record a structured error entry with timestamp and clear separators to onebridge_tui_errors.log."""
    from datetime import datetime
    import traceback

    target_path = Path(log_path or TUI_ERROR_LOG_PATH)
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    exc_type = type(exc).__name__ if exc else "Erro"
    exc_msg = str(exc) if exc else "Sem mensagem descritiva."
    tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)) if exc else "Nenhum traceback disponível."

    sep_major = "=" * 80
    sep_minor = "-" * 80

    lines = [
        sep_major,
        f"[{now_str}] ERRO CAPTURADO NA TUI: {context}",
        sep_minor,
        f"Tipo de Exceção: {exc_type}",
        f"Mensagem:        {exc_msg}",
    ]

    if extra_info:
        for k, v in extra_info.items():
            lines.append(f"{k}: {v}")

    lines.extend([
        "",
        "Traceback Completo:",
        tb_str.strip(),
        sep_major,
        "",
    ])

    entry_text = "\n".join(lines) + "\n"

    try:
        with open(target_path, "a", encoding="utf-8") as f:
            f.write(entry_text)
    except OSError as err:
        logging.getLogger("onebridge").warning(f"Falha ao gravar em {target_path}: {err}")

    # Log to onebridge.log without stderr
    logging.getLogger("onebridge").error(f"[TUI ERROR] {context} - {exc_type}: {exc_msg}")

    return target_path


class _TUIStderrStream:
    """Internal stream that intercepts writes to sys.stderr and logs them to onebridge_tui_errors.log."""

    def __init__(self, log_path: Path, original_stderr: Any):
        self.log_path = log_path
        self.original_stderr = original_stderr
        self._buffer: list[str] = []

    def write(self, s: str) -> int:
        if not s:
            return 0
        self._buffer.append(s)
        if "\n" in s:
            content = "".join(self._buffer).strip()
            self._buffer = []
            if content:
                from datetime import datetime
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                sep_major = "=" * 80
                sep_minor = "-" * 80
                entry = (
                    f"{sep_major}\n"
                    f"[{now_str}] STDERR CAPTURADO DURANTE EXECUÇÃO DA TUI\n"
                    f"{sep_minor}\n"
                    f"{content}\n"
                    f"{sep_major}\n\n"
                )
                try:
                    self.log_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(self.log_path, "a", encoding="utf-8") as f:
                        f.write(entry)
                except OSError:
                    pass
        return len(s)

    def flush(self) -> None:
        if self._buffer:
            content = "".join(self._buffer).strip()
            self._buffer = []
            if content:
                from datetime import datetime
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                sep_major = "=" * 80
                sep_minor = "-" * 80
                entry = (
                    f"{sep_major}\n"
                    f"[{now_str}] STDERR CAPTURADO DURANTE EXECUÇÃO DA TUI\n"
                    f"{sep_minor}\n"
                    f"{content}\n"
                    f"{sep_major}\n\n"
                )
                try:
                    self.log_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(self.log_path, "a", encoding="utf-8") as f:
                        f.write(entry)
                except OSError:
                    pass

    def isatty(self) -> bool:
        return False


class TUIStderrCapture:
    """Context manager that captures sys.stderr to onebridge_tui_errors.log during TUI execution."""

    def __init__(self, log_path: Optional[Path] = None):
        self.log_path = Path(log_path or TUI_ERROR_LOG_PATH)
        self._original_stderr = None

    def __enter__(self):
        self._original_stderr = sys.stderr
        sys.stderr = _TUIStderrStream(self.log_path, self._original_stderr)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._original_stderr is not None:
            try:
                sys.stderr.flush()
            except Exception:
                pass
            sys.stderr = self._original_stderr


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Get a logger instance configured within the OneBridge hierarchy."""
    if not _LOGGING_INITIALIZED:
        setup_logging()

    if not name:
        return logging.getLogger("onebridge")

    if not name.startswith("onebridge"):
        name = f"onebridge.{name}"

    return logging.getLogger(name)
