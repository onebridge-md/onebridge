"""Configuration settings for OneBridge CLI and Microsoft Graph Authentication."""

import os
from pathlib import Path

# Load local .env if present
def _load_env_file():
    for env_path in [Path(".env"), Path.home() / ".onebridge" / ".env"]:
        if env_path.is_file():
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip("'\"")
                            if k not in os.environ:
                                os.environ[k] = v
            except OSError:
                pass

_load_env_file()

DEFAULT_PLACEHOLDER_CLIENT_ID = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"

# Default Microsoft Application (Client) ID
# Supports multi-tenant and personal Microsoft accounts when configured in Azure.
CLIENT_ID: str = os.getenv(
    "ONEBRIDGE_CLIENT_ID",
    os.getenv("ONENOTE_CLIENT_ID", DEFAULT_PLACEHOLDER_CLIENT_ID),
)

# Authority URL - 'common' allows both personal Microsoft accounts (MSA)
# and work/school accounts (Microsoft Entra ID / Microsoft 365).
AUTHORITY: str = os.getenv(
    "ONEBRIDGE_AUTHORITY",
    os.getenv("ONENOTE_AUTHORITY", "https://login.microsoftonline.com/common"),
)

# Microsoft Graph API scopes required for OneNote and profile info.
# Note: MSAL automatically appends reserved OIDC scopes ('openid', 'profile', 'offline_access').
# Passing reserved scopes explicitly to MSAL raises ValueError.
SCOPES: list[str] = [
    "User.Read",
    "Notes.Read",
    "Notes.ReadWrite",
]

# Microsoft Graph API Base URL
GRAPH_API_BASE: str = "https://graph.microsoft.com/v1.0"

# Local SQLite Database Path
DEFAULT_DB_DIR = Path.home() / ".onebridge"
DB_PATH: Path = Path(
    os.getenv(
        "ONEBRIDGE_DB_PATH",
        os.getenv("ONENOTE_DB_PATH", str(DEFAULT_DB_DIR / "auth.db")),
    )
)

# Default Export Output Directory
DEFAULT_EXPORT_DIR: Path = Path(
    os.getenv(
        "ONEBRIDGE_EXPORT_DIR",
        os.getenv("ONENOTE_EXPORT_DIR", "ARQUIVOS"),
    )
)

# Default pause/delay between HTTP requests in milliseconds (anti-throttling)
DEFAULT_REQUEST_DELAY_MS: int = int(
    os.getenv(
        "ONEBRIDGE_REQUEST_DELAY_MS",
        os.getenv("ONENOTE_REQUEST_DELAY_MS", "350"),
    )
)

# Logging configuration
LOG_DIR: Path = Path(
    os.getenv(
        "ONEBRIDGE_LOG_DIR",
        os.getenv("ONENOTE_LOG_DIR", "LOGS"),
    )
)
LOG_FILE: str = os.getenv(
    "ONEBRIDGE_LOG_FILE",
    os.getenv("ONENOTE_LOG_FILE", "onebridge.log"),
)
LOG_LEVEL: str = os.getenv(
    "ONEBRIDGE_LOG_LEVEL",
    os.getenv("ONENOTE_LOG_LEVEL", "INFO"),
).upper()
LOG_FILE_PATH: Path = LOG_DIR / LOG_FILE

# TUI Error Log configuration
TUI_ERROR_LOG_FILE: str = os.getenv(
    "ONEBRIDGE_TUI_ERROR_LOG_FILE",
    "onebridge_tui_errors.log",
)
TUI_ERROR_LOG_PATH: Path = LOG_DIR / TUI_ERROR_LOG_FILE
