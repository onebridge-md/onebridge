"""Unit tests for SettingsService."""

from onebridge.services.settings_service import SettingsService


def test_settings_service_basic_crud(tmp_path):
    db_file = tmp_path / "auth.db"
    settings = SettingsService(db_path=db_file)

    # Initially empty
    assert settings.get("test_key") is None

    # Set and get
    settings.set("test_key", "test_value")
    assert settings.get("test_key") == "test_value"

    # Update
    settings.set("test_key", "new_value")
    assert settings.get("test_key") == "new_value"

    # Delete
    settings.delete("test_key")
    assert settings.get("test_key") is None


def test_settings_service_notebook_defaults(tmp_path):
    db_file = tmp_path / "auth.db"
    settings = SettingsService(db_path=db_file)

    assert settings.get_default_notebook() is None

    settings.set_default_notebook("nb-123", "Caderno de Projetos")
    default_nb = settings.get_default_notebook()
    assert default_nb is not None
    assert default_nb["id"] == "nb-123"
    assert default_nb["name"] == "Caderno de Projetos"

    settings.clear_default_notebook()
    assert settings.get_default_notebook() is None


def test_settings_service_section_defaults(tmp_path):
    db_file = tmp_path / "auth.db"
    settings = SettingsService(db_path=db_file)

    assert settings.get_default_section() is None

    settings.set_default_section("sec-456", "Tarefas", notebook_id="nb-123", notebook_name="Caderno 1")
    default_sec = settings.get_default_section()
    assert default_sec is not None
    assert default_sec["id"] == "sec-456"
    assert default_sec["name"] == "Tarefas"
    assert default_sec["notebook_id"] == "nb-123"
    assert default_sec["notebook_name"] == "Caderno 1"

    all_defs = settings.get_all_defaults()
    assert all_defs["section"]["name"] == "Tarefas"

    settings.clear_all_defaults()
    assert settings.get_default_notebook() is None
    assert settings.get_default_section() is None
