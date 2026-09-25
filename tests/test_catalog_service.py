"""Unit tests for CatalogService."""

from unittest.mock import MagicMock
from onebridge.core.graph_client import OneNoteGraphClient
from onebridge.services.catalog_service import CatalogService


def test_catalog_service_list_notebooks_sorting():
    mock_graph = MagicMock(spec=OneNoteGraphClient)
    mock_graph.get_notebooks.return_value = [
        {
            "id": "nb-1",
            "displayName": "Zeta Notebook",
            "createdDateTime": "2023-01-01T10:00:00Z",
            "lastModifiedDateTime": "2023-05-01T10:00:00Z",
            "isDefault": False,
            "userRole": "Owner",
            "links": {
                "oneNoteWebUrl": {"href": "https://onenote.com/zeta"},
            },
        },
        {
            "id": "nb-2",
            "displayName": "Alpha Notebook",
            "createdDateTime": "2023-02-01T10:00:00Z",
            "lastModifiedDateTime": "2023-06-01T10:00:00Z",
            "isDefault": True,
            "userRole": "Owner",
            "links": {
                "oneNoteWebUrl": {"href": "https://onenote.com/alpha"},
            },
        },
    ]

    service = CatalogService(graph_client=mock_graph)

    # Sort by name ascending
    results_by_name = service.list_notebooks(token="mock_token", sort_by="name", reverse=False)
    assert len(results_by_name) == 2
    assert results_by_name[0].name == "Alpha Notebook"
    assert results_by_name[0].is_default is True
    assert results_by_name[0].web_url == "https://onenote.com/alpha"
    assert results_by_name[1].name == "Zeta Notebook"

    # Sort by modified descending (default)
    results_by_mod = service.list_notebooks(token="mock_token", sort_by="modified", reverse=True)
    assert results_by_mod[0].name == "Alpha Notebook"  # modified in June vs May


def test_catalog_service_get_notebook():
    mock_graph = MagicMock(spec=OneNoteGraphClient)
    mock_graph.get_notebook.return_value = {
        "id": "nb-123",
        "displayName": "Caderno Pessoal",
        "lastModifiedDateTime": "2023-08-10T12:00:00Z",
        "isDefault": True,
        "userRole": "Owner",
    }

    service = CatalogService(graph_client=mock_graph)
    nb = service.get_notebook("nb-123", token="mock_token")
    assert nb.id == "nb-123"
    assert nb.name == "Caderno Pessoal"
    assert nb.is_default is True


def test_catalog_service_resolve_notebook():
    mock_graph = MagicMock(spec=OneNoteGraphClient)
    mock_graph.get_notebook.side_effect = Exception("Not Found")
    mock_graph.get_notebooks.return_value = [
        {"id": "nb-100", "displayName": "Caderno de Trabalho"},
        {"id": "nb-200", "displayName": "Diário Pessoal"},
    ]

    service = CatalogService(graph_client=mock_graph)

    # Resolution by exact name
    nb1 = service.resolve_notebook("Caderno de Trabalho", token="token")
    assert nb1.id == "nb-100"

    # Resolution by lowercase / partial name
    nb2 = service.resolve_notebook("diário", token="token")
    assert nb2.id == "nb-200"

    # Resolution by ID
    nb3 = service.resolve_notebook("nb-100", token="token")
    assert nb3.id == "nb-100"


def test_catalog_service_list_sections_recursive_and_nested():
    mock_graph = MagicMock(spec=OneNoteGraphClient)
    # Direct notebook lookup
    mock_graph.get_notebook.return_value = {"id": "nb-1", "displayName": "Meu Caderno"}
    
    # Direct sections under notebook
    mock_graph.get_notebook_sections.return_value = [
        {
            "id": "sec-root-1",
            "displayName": "Zeta Raiz",
            "createdDateTime": "2023-01-01T00:00:00Z",
            "lastModifiedDateTime": "2023-01-01T00:00:00Z",
            "isDefault": True,
        }
    ]

    # Direct section groups under notebook
    mock_graph.get_notebook_section_groups.return_value = [
        {
            "id": "sg-1",
            "displayName": "Grupo Alfa",
        }
    ]

    # Sections inside Group Alfa
    mock_graph.get_section_group_sections.side_effect = lambda section_group_id, token: (
        [{"id": "sec-sg-1", "displayName": "Beta Seção", "lastModifiedDateTime": "2023-05-01T00:00:00Z"}]
        if section_group_id == "sg-1"
        else [{"id": "sec-sub-1", "displayName": "Alfa Seção Aninhada", "lastModifiedDateTime": "2023-09-01T00:00:00Z"}]
    )

    # Subgroups inside Group Alfa
    mock_graph.get_section_group_section_groups.side_effect = lambda section_group_id, token: (
        [{"id": "sg-sub-1", "displayName": "Subgrupo Beta"}]
        if section_group_id == "sg-1"
        else []
    )

    service = CatalogService(graph_client=mock_graph)

    # 1. Non-recursive (direct only)
    direct_secs = service.list_sections("nb-1", token="token", recursive=False)
    assert len(direct_secs) == 1
    assert direct_secs[0].id == "sec-root-1"
    assert direct_secs[0].parent_path == ""

    # 2. Recursive (traverses all groups and sub-groups)
    all_secs_by_name = service.list_sections("nb-1", token="token", recursive=True, sort_by="name")
    assert len(all_secs_by_name) == 3
    # Sorted by name: "Alfa Seção Aninhada", "Beta Seção", "Zeta Raiz"
    assert all_secs_by_name[0].name == "Alfa Seção Aninhada"
    assert all_secs_by_name[0].parent_path == "Grupo Alfa / Subgrupo Beta"
    assert all_secs_by_name[1].name == "Beta Seção"
    assert all_secs_by_name[1].parent_path == "Grupo Alfa"
    assert all_secs_by_name[2].name == "Zeta Raiz"

    # 3. Sort by modified descending
    all_secs_by_mod = service.list_sections("nb-1", token="token", recursive=True, sort_by="modified", reverse=True)
    assert all_secs_by_mod[0].id == "sec-sub-1"  # Sept 2023

    # 4. Tree retrieval
    tree = service.get_notebook_tree("nb-1", token="token")
    assert tree.notebook.name == "Meu Caderno"
    assert len(tree.sections) == 1
    assert len(tree.section_groups) == 1
    assert tree.section_groups[0].name == "Grupo Alfa"
    assert len(tree.section_groups[0].sections) == 1
    assert len(tree.section_groups[0].section_groups) == 1
    assert tree.section_groups[0].section_groups[0].name == "Subgrupo Beta"
    assert len(tree.section_groups[0].section_groups[0].sections) == 1


def test_catalog_service_resolve_section_and_list_pages():
    mock_graph = MagicMock(spec=OneNoteGraphClient)
    
    # Section resolution mocking
    mock_graph.get_section.side_effect = Exception("Not Found")
    mock_graph.get_notebooks.return_value = [{"id": "nb-1", "displayName": "Caderno 1"}]
    mock_graph.get_notebook.return_value = {"id": "nb-1", "displayName": "Caderno 1"}
    mock_graph.get_notebook_sections.return_value = [
        {"id": "sec-1", "displayName": "Anotações Gerais", "parentNotebook": {"id": "nb-1"}}
    ]
    mock_graph.get_notebook_section_groups.return_value = []

    # Pages mocking
    mock_graph.get_section_pages.return_value = [
        {
            "id": "pg-1",
            "title": "Primeira Página",
            "level": 0,
            "order": 1,
            "createdDateTime": "2023-01-01T00:00:00Z",
            "lastModifiedDateTime": "2023-05-01T00:00:00Z",
        },
        {
            "id": "pg-2",
            "title": "Subpágina",
            "level": 1,
            "order": 2,
            "createdDateTime": "2023-02-01T00:00:00Z",
            "lastModifiedDateTime": "2023-06-01T00:00:00Z",
        },
    ]

    service = CatalogService(graph_client=mock_graph)

    # 1. Resolve section
    sec = service.resolve_section("anotações", token="token")
    assert sec.id == "sec-1"
    assert sec.name == "Anotações Gerais"

    # 2. List pages sorted by order
    pages_by_order = service.list_pages("sec-1", token="token", sort_by="order")
    assert len(pages_by_order) == 2
    assert pages_by_order[0].title == "Primeira Página"
    assert pages_by_order[0].level == 0
    assert pages_by_order[1].title == "Subpágina"
    assert pages_by_order[1].level == 1
    assert pages_by_order[1].parent_section_name == "Anotações Gerais"

    # 3. List pages sorted by title
    pages_by_title = service.list_pages("sec-1", token="token", sort_by="title", reverse=False)
    assert pages_by_title[0].title == "Primeira Página"

    # 4. Get specific page
    mock_graph.get_page.return_value = {"id": "pg-1", "title": "Primeira Página", "level": 0}
    single_page = service.get_page("pg-1", token="token")
    assert single_page.id == "pg-1"
    assert single_page.title == "Primeira Página"


