"""Settings service for persisting and managing user defaults (notebook, section)."""

import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

from onebridge.config import DB_PATH


class SettingsService:
    """Service to persist and retrieve application settings in SQLite."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()

    def get(self, key: str) -> Optional[str]:
        """Retrieve a raw setting value by key."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            if row:
                return row["value"]
        return None

    def set(self, key: str, value: str) -> None:
        """Store or update a setting value."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                (key, value),
            )
            conn.commit()

    def delete(self, key: str) -> None:
        """Delete a setting key."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM settings WHERE key = ?", (key,))
            conn.commit()

    def get_default_notebook(self) -> Optional[Dict[str, str]]:
        """Return the configured default notebook info (id, name) if present."""
        nb_id = self.get("default_notebook_id")
        nb_name = self.get("default_notebook_name")
        if nb_id or nb_name:
            return {"id": nb_id or "", "name": nb_name or ""}
        return None

    def set_default_notebook(self, notebook_id: str, notebook_name: str) -> None:
        """Save default notebook."""
        self.set("default_notebook_id", notebook_id)
        self.set("default_notebook_name", notebook_name)

    def clear_default_notebook(self) -> None:
        """Remove default notebook configuration."""
        self.delete("default_notebook_id")
        self.delete("default_notebook_name")

    def get_default_section(self) -> Optional[Dict[str, str]]:
        """Return the configured default section info (id, name, notebook_id, notebook_name) if present."""
        sec_id = self.get("default_section_id")
        sec_name = self.get("default_section_name")
        sec_nb_id = self.get("default_section_notebook_id")
        sec_nb_name = self.get("default_section_notebook_name")
        if sec_id or sec_name:
            return {
                "id": sec_id or "",
                "name": sec_name or "",
                "notebook_id": sec_nb_id or "",
                "notebook_name": sec_nb_name or "",
            }
        return None

    def set_default_section(
        self,
        section_id: str,
        section_name: str,
        notebook_id: Optional[str] = None,
        notebook_name: Optional[str] = None,
    ) -> None:
        """Save default section with optional associated notebook."""
        self.set("default_section_id", section_id)
        self.set("default_section_name", section_name)
        if notebook_id:
            self.set("default_section_notebook_id", notebook_id)
        else:
            self.delete("default_section_notebook_id")
        if notebook_name:
            self.set("default_section_notebook_name", notebook_name)
        else:
            self.delete("default_section_notebook_name")

    def clear_default_section(self) -> None:
        """Remove default section configuration."""
        self.delete("default_section_id")
        self.delete("default_section_name")
        self.delete("default_section_notebook_id")
        self.delete("default_section_notebook_name")

    def get_all_defaults(self) -> Dict[str, Any]:
        """Return a combined dictionary of all configured defaults."""
        return {
            "notebook": self.get_default_notebook(),
            "section": self.get_default_section(),
        }

    def clear_all_defaults(self) -> None:
        """Clear both notebook and section defaults."""
        self.clear_default_notebook()
        self.clear_default_section()
