"""SQLite-backed Token Cache for MSAL (Microsoft Authentication Library).

Provides persistent and encrypted storage for OAuth access and refresh tokens,
allowing silent token renewal across CLI invocations without re-prompting the user.
"""

import base64
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

import msal
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from onebridge.logger import get_logger

logger = get_logger("onebridge.auth.sqlite_cache")


def _get_encryption_key(db_dir: Path) -> bytes:
    """Generate or retrieve a machine-local encryption key for protecting tokens at rest."""
    key_file = db_dir / ".secret_key"
    if key_file.exists():
        return key_file.read_bytes()

    # Create directory if missing
    db_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate a salt and key
    salt = os.urandom(16)
    # Use machine/user identifiers as baseline entropy
    user_entropy = f"{os.getenv('USER', 'default_user')}@{os.uname().nodename if hasattr(os, 'uname') else 'localhost'}"
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(user_entropy.encode() + os.urandom(32)))
    
    # Save with restrictive permissions
    key_file.write_bytes(key)
    try:
        os.chmod(key_file, 0o600)
    except OSError:
        pass
    return key


class SQLiteTokenCache(msal.SerializableTokenCache):
    """Custom MSAL SerializableTokenCache backed by an encrypted SQLite database."""

    def __init__(self, db_path: Path):
        super().__init__()
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.cipher = Fernet(_get_encryption_key(self.db_path.parent))
        self._init_db()
        self._load()

    def _get_connection(self) -> sqlite3.Connection:
        """Create a connection to the SQLite database with safe settings."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initialize the token cache database table."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS token_cache (
                    id TEXT PRIMARY KEY,
                    username TEXT,
                    account_id TEXT,
                    tenant_id TEXT,
                    client_id TEXT,
                    authority TEXT,
                    cache_blob BLOB NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            # Migration for existing databases that don't have client_id or authority columns
            cursor = conn.execute("PRAGMA table_info(token_cache)")
            columns = {row["name"] for row in cursor.fetchall()}
            if "client_id" not in columns:
                try:
                    conn.execute("ALTER TABLE token_cache ADD COLUMN client_id TEXT")
                except sqlite3.OperationalError:
                    pass
            if "authority" not in columns:
                try:
                    conn.execute("ALTER TABLE token_cache ADD COLUMN authority TEXT")
                except sqlite3.OperationalError:
                    pass
            conn.commit()

    def _load(self) -> None:
        """Load and decrypt the token cache from SQLite."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT cache_blob FROM token_cache WHERE id = 'default_account' LIMIT 1"
            ).fetchone()
            if row and row["cache_blob"]:
                try:
                    decrypted_data = self.cipher.decrypt(row["cache_blob"]).decode("utf-8")
                    self.deserialize(decrypted_data)
                    logger.debug("Cache de tokens carregado com sucesso do SQLite.")
                except Exception as e:
                    logger.warning(f"Falha ao descriptografar cache de tokens do SQLite: {e}")
                    pass

    def get_stored_client_id(self) -> Optional[str]:
        """Inspect the deserialized token cache dictionary to find any stored client_id."""
        try:
            raw_cache = json.loads(self.serialize())
            for token_type in ["AccessToken", "RefreshToken", "IdToken", "AppMetadata"]:
                tokens = raw_cache.get(token_type, {})
                for item in tokens.values():
                    cid = item.get("client_id")
                    if cid:
                        return cid
        except Exception:
            pass
        return None

    def save_if_changed(
        self,
        username: Optional[str] = None,
        account_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        client_id: Optional[str] = None,
        authority: Optional[str] = None,
        force: bool = False,
    ) -> None:
        """Encrypt and persist the token cache to SQLite if state has changed or force=True."""
        if self.has_state_changed or force:
            serialized_cache = self.serialize()
            encrypted_blob = self.cipher.encrypt(serialized_cache.encode("utf-8"))

            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO token_cache (id, username, account_id, tenant_id, client_id, authority, cache_blob, updated_at)
                    VALUES ('default_account', ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(id) DO UPDATE SET
                        username = coalesce(excluded.username, token_cache.username),
                        account_id = coalesce(excluded.account_id, token_cache.account_id),
                        tenant_id = coalesce(excluded.tenant_id, token_cache.tenant_id),
                        client_id = coalesce(excluded.client_id, token_cache.client_id),
                        authority = coalesce(excluded.authority, token_cache.authority),
                        cache_blob = excluded.cache_blob,
                        updated_at = CURRENT_TIMESTAMP;
                    """,
                    (username, account_id, tenant_id, client_id, authority, encrypted_blob),
                )
                conn.commit()
            logger.debug(f"Cache de tokens persistido no SQLite (user: {username}, client_id: {client_id}).")
            self.has_state_changed = False

    def clear(self) -> None:
        """Clear the cache in memory and remove records from SQLite."""
        # Deserializing empty JSON clears MSAL internal dictionary
        self.deserialize("{}")
        with self._get_connection() as conn:
            conn.execute("DELETE FROM token_cache WHERE id = 'default_account'")
            conn.commit()
        logger.info("Cache de tokens removido do SQLite.")
        self.has_state_changed = False

    def get_account_metadata(self) -> Optional[Dict[str, Any]]:
        """Retrieve stored account metadata."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT username, account_id, tenant_id, client_id, authority, updated_at FROM token_cache WHERE id = 'default_account' LIMIT 1"
            ).fetchone()
            if row:
                return dict(row)
        return None
