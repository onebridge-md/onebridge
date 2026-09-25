"""Unit tests for OneBridge logging infrastructure."""

import logging
import re
from pathlib import Path
from unittest.mock import patch

from onebridge.logger import (
    OneBridgeFormatter,
    StderrErrorFilter,
    get_log_level,
    get_logger,
    setup_logging,
)


def test_log_level_resolution():
    """Test resolving string log levels to logging integers."""
    assert get_log_level("DEBUG") == logging.DEBUG
    assert get_log_level("INFO") == logging.INFO
    assert get_log_level("WARNING") == logging.WARNING
    assert get_log_level("ERROR") == logging.ERROR
    assert get_log_level("invalid") == logging.INFO


def test_custom_formatter_format():
    """Test that formatter follows [YYYY-MM-DD hh:mm:ss] - [modulo] - [mensagem]."""
    formatter = OneBridgeFormatter()
    record = logging.LogRecord(
        name="onebridge.test.module",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Teste de mensagem de log",
        args=(),
        exc_info=None,
    )
    formatted = formatter.format(record)

    pattern = r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] - \[onebridge\.test\.module\] - \[Teste de mensagem de log\]$"
    assert re.match(pattern, formatted) is not None


def test_custom_formatter_with_exception():
    """Test that formatter includes stack trace when exception info is present."""
    formatter = OneBridgeFormatter()
    try:
        raise ValueError("Exemplo de erro fatal")
    except ValueError:
        import sys
        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="onebridge.core.test",
        level=logging.ERROR,
        pathname="test.py",
        lineno=25,
        msg="Ocorreu uma falha",
        args=(),
        exc_info=exc_info,
    )
    formatted = formatter.format(record)

    assert "[onebridge.core.test] - [Ocorreu uma falha]" in formatted
    assert "Traceback (most recent call last):" in formatted
    assert "ValueError: Exemplo de erro fatal" in formatted


def test_stderr_error_filter():
    """Test that StderrErrorFilter only passes ERROR and above."""
    filter_ = StderrErrorFilter()

    debug_record = logging.LogRecord("test", logging.DEBUG, "path", 1, "msg", (), None)
    info_record = logging.LogRecord("test", logging.INFO, "path", 1, "msg", (), None)
    warn_record = logging.LogRecord("test", logging.WARNING, "path", 1, "msg", (), None)
    error_record = logging.LogRecord("test", logging.ERROR, "path", 1, "msg", (), None)
    critical_record = logging.LogRecord("test", logging.CRITICAL, "path", 1, "msg", (), None)

    assert not filter_.filter(debug_record)
    assert not filter_.filter(info_record)
    assert not filter_.filter(warn_record)
    assert filter_.filter(error_record)
    assert filter_.filter(critical_record)


def test_setup_logging_creates_directory_and_writes_file(tmp_path):
    """Test setup_logging automatically creates log directory and writes logs."""
    log_dir = tmp_path / "custom_logs"
    log_file = log_dir / "test_onebridge.log"

    assert not log_dir.exists()

    setup_logging(log_level="DEBUG", log_file_path=log_file, force=True)
    assert log_dir.exists()

    logger = get_logger("onebridge.auth.client")
    logger.debug("Mensagem de debug")
    logger.info("Mensagem informativa")
    logger.warning("Mensagem de alerta")
    logger.error("Mensagem de erro")

    content = log_file.read_text(encoding="utf-8")
    assert "[onebridge.auth.client] - [Mensagem de debug]" in content
    assert "[onebridge.auth.client] - [Mensagem informativa]" in content
    assert "[onebridge.auth.client] - [Mensagem de alerta]" in content
    assert "[onebridge.auth.client] - [Mensagem de erro]" in content


def test_log_level_filtering(tmp_path):
    """Test that messages below configured log level are ignored in file."""
    log_file = tmp_path / "info_level.log"

    setup_logging(log_level="INFO", log_file_path=log_file, force=True)

    logger = get_logger("onebridge.services.export")
    logger.debug("Ignorar debug")
    logger.info("Aceitar info")
    logger.warning("Aceitar warning")
    logger.error("Aceitar error")

    content = log_file.read_text(encoding="utf-8")
    assert "Ignorar debug" not in content
    assert "Aceitar info" in content
    assert "Aceitar warning" in content
    assert "Aceitar error" in content


def test_get_logger_namespacing():
    """Test that get_logger automatically prefixes names with 'onebridge.'."""
    logger1 = get_logger("api.client")
    logger2 = get_logger("onebridge.api.client")
    logger3 = get_logger()

    assert logger1.name == "onebridge.api.client"
    assert logger2.name == "onebridge.api.client"
    assert logger3.name == "onebridge"


def test_stderr_handler_output(tmp_path, capsys):
    """Test that ERROR logs are emitted to STDERR while INFO/DEBUG/WARNING are not."""
    log_file = tmp_path / "stderr_test.log"
    setup_logging(log_level="DEBUG", log_file_path=log_file, force=True)

    logger = get_logger("onebridge.cli.main")
    logger.debug("Debug msg")
    logger.info("Info msg")
    logger.warning("Warning msg")

    captured = capsys.readouterr()
    assert captured.err == ""

    try:
        raise RuntimeError("Falha crítica no teste")
    except RuntimeError:
        logger.error("Erro ocorreu durante a execução", exc_info=True)

    captured = capsys.readouterr()
    assert "[onebridge.cli.main] - [Erro ocorreu durante a execução]" in captured.err
    assert "Traceback (most recent call last):" in captured.err
    assert "RuntimeError: Falha crítica no teste" in captured.err


def test_setup_logging_disable_stderr(tmp_path, capsys):
    """Test that setting enable_stderr=False prevents any STDERR output."""
    from onebridge.logger import enable_stderr_logging

    log_file = tmp_path / "no_stderr.log"
    setup_logging(log_level="DEBUG", log_file_path=log_file, force=True, enable_stderr=False)

    logger = get_logger("onebridge.tui")
    logger.error("Erro que não deve ir para STDERR")

    captured = capsys.readouterr()
    assert captured.err == ""

    # Re-enable
    enable_stderr_logging(True)


def test_log_tui_error_format_and_separators(tmp_path):
    """Test log_tui_error writes structured entry with timestamp, separators and stack trace."""
    from onebridge.logger import log_tui_error

    error_log = tmp_path / "onebridge_tui_errors.log"

    try:
        raise ConnectionResetError("Conexão perdida com o servidor")
    except ConnectionResetError as exc:
        saved_path = log_tui_error(
            context="Teste de falha de conexão",
            exc=exc,
            log_path=error_log,
            extra_info={"Caderno": "Meu Caderno", "ID": "nb-123"},
        )

    assert saved_path == error_log
    assert error_log.exists()
    content = error_log.read_text(encoding="utf-8")

    # Verify timestamp format
    assert re.search(r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] ERRO CAPTURADO NA TUI: Teste de falha de conexão", content) is not None

    # Verify major and minor separators
    assert "=" * 80 in content
    assert "-" * 80 in content

    # Verify metadata and exception details
    assert "Tipo de Exceção: ConnectionResetError" in content
    assert "Mensagem:        Conexão perdida com o servidor" in content
    assert "Caderno: Meu Caderno" in content
    assert "ID: nb-123" in content

    # Verify traceback
    assert "Traceback Completo:" in content
    assert "ConnectionResetError: Conexão perdida com o servidor" in content


def test_tui_stderr_capture(tmp_path, capsys):
    """Test TUIStderrCapture redirects raw stderr writes to log file without polluting terminal."""
    import sys
    from onebridge.logger import TUIStderrCapture

    tui_log = tmp_path / "captured_stderr.log"

    with TUIStderrCapture(log_path=tui_log):
        sys.stderr.write("Aviso gerado por biblioteca de terceiros\n")
        sys.stderr.flush()

    # Raw stderr should have received nothing
    captured = capsys.readouterr()
    assert captured.err == ""

    # Log file should contain the captured stderr with timestamp and separators
    assert tui_log.exists()
    content = tui_log.read_text(encoding="utf-8")
    assert "=" * 80 in content
    assert "STDERR CAPTURADO DURANTE EXECUÇÃO DA TUI" in content
    assert "Aviso gerado por biblioteca de terceiros" in content

