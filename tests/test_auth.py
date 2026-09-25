"""Unit tests for SQLite Token Cache and OneBridge Authenticator."""

import json
import sqlite3
from unittest.mock import MagicMock, patch
import pytest

from onebridge.auth.client import OneNoteAuthenticator
from onebridge.auth.sqlite_cache import SQLiteTokenCache


def test_sqlite_cache_initialization(tmp_path):
    """Test that SQLite database and token_cache table are properly initialized."""
    db_file = tmp_path / "auth.db"
    cache = SQLiteTokenCache(db_path=db_file)

    assert db_file.exists()
    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='token_cache';")
        assert cursor.fetchone() is not None


def test_sqlite_cache_save_load_clear(tmp_path):
    """Test persisting token cache state, encrypting, reloading and clearing."""
    db_file = tmp_path / "auth.db"
    cache1 = SQLiteTokenCache(db_path=db_file)

    # Simulate MSAL internal cache state modification
    sample_data = {"AccessToken": {"key1": {"secret": "mock_access_token_xyz", "client_id": "custom-cid-123"}}}
    cache1.deserialize(json.dumps(sample_data))
    cache1.has_state_changed = True
    cache1.save_if_changed(
        username="user@example.com",
        account_id="acc-123",
        tenant_id="tid-456",
        client_id="custom-cid-123",
        authority="https://login.microsoftonline.com/common",
    )

    assert not cache1.has_state_changed

    # Metadata should be retrievable
    meta = cache1.get_account_metadata()
    assert meta is not None
    assert meta["username"] == "user@example.com"
    assert meta["account_id"] == "acc-123"
    assert meta["client_id"] == "custom-cid-123"

    # Instantiate a second cache instance pointing to the same SQLite DB to test re-hydration
    cache2 = SQLiteTokenCache(db_path=db_file)
    deserialized = json.loads(cache2.serialize())
    assert "AccessToken" in deserialized
    assert deserialized["AccessToken"]["key1"]["secret"] == "mock_access_token_xyz"
    assert cache2.get_stored_client_id() == "custom-cid-123"

    # Test clear
    cache2.clear()
    assert cache2.get_account_metadata() is None
    assert json.loads(cache2.serialize()) == {}


def test_authenticator_auto_recovers_client_id_from_cache(tmp_path):
    """Test that OneNoteAuthenticator automatically uses the client_id stored in DB if none provided."""
    db_file = tmp_path / "auth.db"
    cache = SQLiteTokenCache(db_path=db_file)
    sample_data = {"AccessToken": {"key1": {"client_id": "saved-app-id-777"}}}
    cache.deserialize(json.dumps(sample_data))
    cache.save_if_changed(client_id="saved-app-id-777", force=True)

    auth = OneNoteAuthenticator(db_path=db_file)
    assert auth.client_id == "saved-app-id-777"


def test_authenticator_filters_reserved_scopes(tmp_path):
    """Test that reserved OIDC scopes (offline_access, openid, profile) are sanitized."""
    db_file = tmp_path / "auth.db"
    auth = OneNoteAuthenticator(
        db_path=db_file,
        scopes=["User.Read", "Notes.Read", "offline_access", "openid", "profile"],
    )
    assert "offline_access" not in auth.scopes
    assert "openid" not in auth.scopes
    assert "profile" not in auth.scopes
    assert "User.Read" in auth.scopes
    assert "Notes.Read" in auth.scopes


def test_authenticator_silent_flow_success(tmp_path):
    """Test silent token acquisition when account is present in cache."""
    db_file = tmp_path / "auth.db"
    auth = OneNoteAuthenticator(db_path=db_file)

    mock_account = {"home_account_id": "acc-123", "username": "user@example.com"}
    mock_token_result = {
        "access_token": "valid_mock_token_123",
        "id_token_claims": {"preferred_username": "user@example.com", "sub": "acc-123"},
    }

    with patch.object(auth.app, "get_accounts", return_value=[mock_account]), \
         patch.object(auth.app, "acquire_token_silent", return_value=mock_token_result):
        
        token = auth.get_valid_token()
        assert token == "valid_mock_token_123"


def test_authenticator_unauthenticated_raises(tmp_path):
    """Test that get_valid_token raises RuntimeError when unauthenticated."""
    db_file = tmp_path / "auth.db"
    auth = OneNoteAuthenticator(db_path=db_file)

    with patch.object(auth.app, "get_accounts", return_value=[]):
        with pytest.raises(RuntimeError, match="Nenhuma sessão ativa"):
            auth.get_valid_token()


def test_authenticator_device_flow_success(tmp_path):
    """Test successful device code flow and persistence."""
    db_file = tmp_path / "auth.db"
    auth = OneNoteAuthenticator(db_path=db_file)

    mock_flow = {
        "user_code": "ABCD-1234",
        "message": "Visit https://microsoft.com/devicelogin and enter code ABCD-1234",
    }
    mock_result = {
        "access_token": "device_token_xyz",
        "id_token_claims": {
            "preferred_username": "dev@example.com",
            "oid": "user-oid-789",
            "tid": "common",
        },
    }

    prompt_messages = []

    with patch.object(auth.app, "initiate_device_flow", return_value=mock_flow), \
         patch.object(auth.app, "acquire_token_by_device_flow", return_value=mock_result):
        
        res = auth.login_device_flow(prompt_callback=lambda msg: prompt_messages.append(msg))
        assert res["access_token"] == "device_token_xyz"
        assert len(prompt_messages) == 1
        assert "ABCD-1234" in prompt_messages[0]

        # Verify SQLite cache recorded the account
        meta = auth.get_cached_metadata()
        assert meta is not None
        assert meta["username"] == "dev@example.com"
