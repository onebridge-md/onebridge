"""Unit tests for OneBridgeAPI facade."""

from unittest.mock import MagicMock, patch
import pytest

from onebridge.api.client import OneBridgeAPI
from onebridge.api.dto import NotebookDTO
from onebridge.auth.client import OneNoteAuthenticator
from onebridge.services.catalog_service import CatalogService


def test_api_list_notebooks_authenticated():
    mock_auth = MagicMock(spec=OneNoteAuthenticator)
    mock_auth.get_valid_token.return_value = "valid_token_123"

    mock_catalog = MagicMock(spec=CatalogService)
    mock_dto = NotebookDTO(id="nb-1", name="Meu Caderno", is_default=True)
    mock_catalog.list_notebooks.return_value = [mock_dto]

    api = OneBridgeAPI(authenticator=mock_auth, catalog_service=mock_catalog)
    notebooks = api.list_notebooks()

    assert len(notebooks) == 1
    assert notebooks[0].id == "nb-1"
    assert notebooks[0].name == "Meu Caderno"
    mock_auth.get_valid_token.assert_called_once()
    mock_catalog.list_notebooks.assert_called_once_with(token="valid_token_123", sort_by="modified", reverse=True)


def test_api_list_notebooks_unauthenticated_raises():
    mock_auth = MagicMock(spec=OneNoteAuthenticator)
    mock_auth.get_valid_token.side_effect = RuntimeError("Nenhuma sessão ativa")

    api = OneBridgeAPI(authenticator=mock_auth)
    with pytest.raises(RuntimeError, match="Nenhuma sessão ativa"):
        api.list_notebooks()


def test_api_list_sections_and_tree():
    mock_auth = MagicMock(spec=OneNoteAuthenticator)
    mock_auth.get_valid_token.return_value = "token_abc"

    mock_catalog = MagicMock(spec=CatalogService)
    from onebridge.api.dto import NotebookTreeDTO, SectionDTO
    mock_sec = SectionDTO(id="sec-1", name="Seção 1")
    mock_catalog.list_sections.return_value = [mock_sec]
    mock_catalog.get_notebook_tree.return_value = NotebookTreeDTO(
        notebook=NotebookDTO(id="nb-1", name="Caderno"),
        sections=[mock_sec],
        section_groups=[],
    )
    mock_catalog.get_section.return_value = mock_sec

    api = OneBridgeAPI(authenticator=mock_auth, catalog_service=mock_catalog)

    # 1. list_sections
    secs = api.list_sections("Meu Caderno", recursive=True, sort_by="name", reverse=False)
    assert len(secs) == 1
    assert secs[0].name == "Seção 1"
    mock_catalog.list_sections.assert_called_once_with(
        notebook_id_or_name="Meu Caderno",
        token="token_abc",
        recursive=True,
        sort_by="name",
        reverse=False,
    )

    # 2. get_notebook_tree
    tree = api.get_notebook_tree("nb-1")
    assert tree.notebook.id == "nb-1"
    assert len(tree.sections) == 1
    mock_catalog.get_notebook_tree.assert_called_once_with(
        notebook_id_or_name="nb-1",
        token="token_abc",
    )

    # 3. get_section
    sec = api.get_section("sec-1")
    assert sec.id == "sec-1"
    mock_catalog.get_section.assert_called_once_with(
        section_id="sec-1",
        token="token_abc",
    )


def test_api_pages_and_defaults(tmp_path):
    db_file = tmp_path / "auth.db"
    mock_auth = MagicMock(spec=OneNoteAuthenticator)
    mock_auth.get_valid_token.return_value = "token_xyz"

    mock_catalog = MagicMock(spec=CatalogService)
    from onebridge.api.dto import PageDTO, SectionDTO
    mock_page = PageDTO(id="pg-1", title="Minha Nota", level=0, parent_section_name="Seção A")
    mock_catalog.list_pages.return_value = [mock_page]
    mock_catalog.resolve_notebook.return_value = NotebookDTO(id="nb-1", name="Meu Caderno")
    mock_catalog.resolve_section.return_value = SectionDTO(id="sec-1", name="Seção A", parent_notebook_id="nb-1")
    mock_catalog.get_page.return_value = mock_page

    api = OneBridgeAPI(authenticator=mock_auth, catalog_service=mock_catalog, db_path=db_file)

    # 1. Without default and without argument -> raises ValueError
    with pytest.raises(ValueError, match="Nenhuma seção informada e nenhuma seção padrão"):
        api.list_pages()

    # 2. Set default notebook & section
    nb = api.set_default_notebook("Meu Caderno")
    assert nb.name == "Meu Caderno"
    sec = api.set_default_section("Seção A")
    assert sec.name == "Seção A"

    defs = api.get_defaults()
    assert defs["notebook"]["name"] == "Meu Caderno"
    assert defs["section"]["name"] == "Seção A"

    # 3. list_pages using saved defaults
    pages = api.list_pages()
    assert len(pages) == 1
    assert pages[0].title == "Minha Nota"
    mock_catalog.list_pages.assert_called_with(
        section_id_or_name="sec-1",
        token="token_xyz",
        notebook_id_or_name="nb-1",
        sort_by="order",
        reverse=False,
    )

    # 4. get_page
    p = api.get_page("pg-1")
    assert p.id == "pg-1"

    # 5. clear defaults
    api.clear_defaults("section")
    assert api.get_defaults()["section"] is None
    assert api.get_defaults()["notebook"] is not None
    api.clear_defaults()
    assert api.get_defaults()["notebook"] is None


def test_api_section_group_methods_and_graph_client_property():
    mock_auth = MagicMock(spec=OneNoteAuthenticator)
    mock_auth.get_valid_token.return_value = "token_sg"

    mock_catalog = MagicMock(spec=CatalogService)
    from onebridge.api.dto import SectionDTO, SectionGroupDTO
    mock_sec = SectionDTO(id="sec-sg-1", name="Seção em Grupo")
    mock_group = SectionGroupDTO(id="sg-sub-1", name="Subgrupo")

    mock_catalog.list_section_group_sections.return_value = [mock_sec]
    mock_catalog.list_section_group_section_groups.return_value = [mock_group]
    mock_catalog.list_sections_in_section_group.return_value = [mock_sec]
    mock_catalog.graph_client = MagicMock()

    api = OneBridgeAPI(authenticator=mock_auth, catalog_service=mock_catalog)

    # 1. graph_client property
    assert api.graph_client is mock_catalog.graph_client

    # 2. list_section_group_sections
    secs = api.list_section_group_sections("sg-1", parent_path="RECEITAS")
    assert len(secs) == 1
    assert secs[0].name == "Seção em Grupo"
    mock_catalog.list_section_group_sections.assert_called_once_with(
        section_group_id="sg-1", token="token_sg", parent_path="RECEITAS"
    )

    # 3. list_section_group_section_groups
    groups = api.list_section_group_section_groups("sg-1", parent_path="RECEITAS")
    assert len(groups) == 1
    assert groups[0].name == "Subgrupo"
    mock_catalog.list_section_group_section_groups.assert_called_once_with(
        section_group_id="sg-1", token="token_sg", parent_path="RECEITAS"
    )

    # 4. list_sections_in_section_group
    all_secs = api.list_sections_in_section_group("sg-1", recursive=True)
    assert len(all_secs) == 1
    assert all_secs[0].id == "sec-sg-1"
    mock_catalog.list_sections_in_section_group.assert_called_once_with(
        section_group_id="sg-1", token="token_sg", recursive=True
    )



