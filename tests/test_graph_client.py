"""Unit tests for OneNoteGraphClient."""

from unittest.mock import MagicMock, patch
import pytest
import requests

from onebridge.core.graph_client import (
    GraphAPIError,
    GraphAuthError,
    GraphNotFoundError,
    OneNoteGraphClient,
)


def test_graph_client_get_success():
    client = OneNoteGraphClient()
    mock_response = MagicMock(spec=requests.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": "123", "displayName": "Meu Caderno"}

    with patch("requests.get", return_value=mock_response) as mock_get:
        data = client.get("me/onenote/notebooks/123", token="mock_token_abc")
        assert data["id"] == "123"
        assert data["displayName"] == "Meu Caderno"
        mock_get.assert_called_once()
        headers = mock_get.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer mock_token_abc"


def test_graph_client_pagination():
    client = OneNoteGraphClient()

    page1_response = MagicMock(spec=requests.Response)
    page1_response.status_code = 200
    page1_response.json.return_value = {
        "value": [{"id": "nb-1", "displayName": "Caderno 1"}],
        "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/onenote/notebooks?skip=1",
    }

    page2_response = MagicMock(spec=requests.Response)
    page2_response.status_code = 200
    page2_response.json.return_value = {
        "value": [{"id": "nb-2", "displayName": "Caderno 2"}],
    }

    with patch("requests.get", side_effect=[page1_response, page2_response]) as mock_get:
        items = client.get_paginated("me/onenote/notebooks", token="mock_token")
        assert len(items) == 2
        assert items[0]["id"] == "nb-1"
        assert items[1]["id"] == "nb-2"
        assert mock_get.call_count == 2


def test_graph_client_401_auth_error():
    client = OneNoteGraphClient()
    mock_response = MagicMock(spec=requests.Response)
    mock_response.status_code = 401
    mock_response.text = "Unauthorized"

    with patch("requests.get", return_value=mock_response):
        with pytest.raises(GraphAuthError, match="Sessão expirada"):
            client.get("me/onenote/notebooks", token="expired_token")


def test_graph_client_404_not_found():
    client = OneNoteGraphClient()
    mock_response = MagicMock(spec=requests.Response)
    mock_response.status_code = 404
    mock_response.text = "Not Found"

    with patch("requests.get", return_value=mock_response):
        with pytest.raises(GraphNotFoundError, match="não encontrado"):
            client.get("me/onenote/notebooks/invalid-id", token="token")


def test_graph_client_429_throttling():
    client = OneNoteGraphClient()
    mock_response = MagicMock(spec=requests.Response)
    mock_response.status_code = 429
    mock_response.headers = {"Retry-After": "10"}
    mock_response.text = "Too Many Requests"

    with patch("requests.get", return_value=mock_response):
        with pytest.raises(GraphAPIError, match="Limite de requisições excedido"):
            client.get("me/onenote/notebooks", token="token")


def test_graph_client_sections_and_groups():
    client = OneNoteGraphClient()

    with patch.object(client, "get_paginated") as mock_paginated:
        mock_paginated.return_value = [{"id": "sec-1", "displayName": "Seção 1"}]

        res_sections = client.get_notebook_sections("nb-123", token="token")
        assert len(res_sections) == 1
        mock_paginated.assert_called_with("me/onenote/notebooks/nb-123/sections", "token")

        res_groups = client.get_notebook_section_groups("nb-123", token="token")
        assert len(res_groups) == 1
        mock_paginated.assert_called_with("me/onenote/notebooks/nb-123/sectionGroups", "token")

        res_sg_sections = client.get_section_group_sections("sg-456", token="token")
        assert len(res_sg_sections) == 1
        mock_paginated.assert_called_with("me/onenote/sectionGroups/sg-456/sections", "token")

        res_sg_groups = client.get_section_group_section_groups("sg-456", token="token")
        assert len(res_sg_groups) == 1
        mock_paginated.assert_called_with("me/onenote/sectionGroups/sg-456/sectionGroups", "token")

    with patch.object(client, "get") as mock_get:
        mock_get.return_value = {"id": "sec-1", "displayName": "Seção 1"}
        res_sec = client.get_section("sec-1", token="token")
        assert res_sec["id"] == "sec-1"
        mock_get.assert_called_with("me/onenote/sections/sec-1", "token")


def test_graph_client_pages():
    client = OneNoteGraphClient()

    with patch.object(client, "get_paginated") as mock_paginated:
        mock_paginated.return_value = [{"id": "page-1", "title": "Página 1", "level": 0}]

        pages = client.get_section_pages("sec-123", token="token")
        assert len(pages) == 1
        assert pages[0]["title"] == "Página 1"
        mock_paginated.assert_called_with(
            "me/onenote/sections/sec-123/pages",
            "token",
            params={"pagelevel": "true"},
        )

        pages_sorted = client.get_section_pages("sec-123", token="token", order_by="lastModifiedDateTime desc")
        mock_paginated.assert_called_with(
            "me/onenote/sections/sec-123/pages",
            "token",
            params={"pagelevel": "true", "$orderby": "lastModifiedDateTime desc"},
        )

    with patch.object(client, "get") as mock_get:
        mock_get.return_value = {"id": "page-1", "title": "Página 1"}
        page = client.get_page("page-1", token="token")
        assert page["id"] == "page-1"
        mock_get.assert_called_with("me/onenote/pages/page-1", "token", params={"pagelevel": "true"})


def test_graph_client_rate_limiting():
    client = OneNoteGraphClient(request_delay_ms=200)
    assert client.request_delay_seconds == 0.2

    mock_resp = MagicMock(spec=requests.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"ok": True}

    with patch("requests.get", return_value=mock_resp), patch("time.sleep") as mock_sleep:
        client.get("test1", token="tok")
        assert mock_sleep.call_count == 0  # First request doesn't sleep

        client.get("test2", token="tok")
        assert mock_sleep.call_count == 1  # Second request sleeps

    client.set_request_delay_ms(500)
    assert client.request_delay_seconds == 0.5


