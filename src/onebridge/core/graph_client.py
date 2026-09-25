import time
from typing import Any, Dict, List, Optional
import requests

from onebridge.config import DEFAULT_REQUEST_DELAY_MS, GRAPH_API_BASE
from onebridge.logger import get_logger

logger = get_logger("onebridge.core.graph_client")


class GraphAPIError(Exception):
    """Base exception for Microsoft Graph API errors."""

    def __init__(self, message: str, status_code: Optional[int] = None, response_body: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class GraphAuthError(GraphAPIError):
    """Raised when authentication fails (HTTP 401 / 403)."""
    pass


class GraphNotFoundError(GraphAPIError):
    """Raised when the requested resource is not found (HTTP 404)."""
    pass


class OneNoteGraphClient:
    """Client for executing requests against Microsoft Graph OneNote endpoints."""

    def __init__(
        self,
        base_url: str = GRAPH_API_BASE,
        timeout: int = 15,
        request_delay_ms: int = DEFAULT_REQUEST_DELAY_MS,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.request_delay_seconds = max(0.0, float(request_delay_ms) / 1000.0)
        self._last_request_time: Optional[float] = None

    def set_request_delay_ms(self, delay_ms: int) -> None:
        """Dynamically adjust request delay in milliseconds."""
        self.request_delay_seconds = max(0.0, float(delay_ms) / 1000.0)

    def _apply_rate_limit(self) -> None:
        """Enforces configured pause between consecutive HTTP requests."""
        if self.request_delay_seconds > 0 and self._last_request_time is not None:
            elapsed = time.time() - self._last_request_time
            if elapsed < self.request_delay_seconds:
                pause_time = self.request_delay_seconds - elapsed
                logger.debug(f"Aplicando pausa de taxa de requisição: {pause_time:.3f}s")
                time.sleep(pause_time)
        self._last_request_time = time.time()

    def _build_headers(self, token: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "OneBridge-CLI/0.1.0",
        }

    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 401:
            logger.error(f"Erro de autenticação HTTP 401: {response.text}")
            raise GraphAuthError(
                "Sessão expirada ou token de acesso inválido no Microsoft Graph. Execute 'onebridge login'.",
                status_code=401,
                response_body=response.text,
            )
        elif response.status_code == 403:
            logger.error(f"Acesso proibido HTTP 403: {response.text}")
            raise GraphAuthError(
                "Acesso negado às notas do OneNote. Verifique as permissões de escopo da conta.",
                status_code=403,
                response_body=response.text,
            )
        elif response.status_code == 404:
            url_str = getattr(response, "url", "unknown")
            logger.warning(f"Recurso não encontrado HTTP 404: {url_str}")
            raise GraphNotFoundError(
                "Recurso do OneNote não encontrado.",
                status_code=404,
                response_body=getattr(response, "text", ""),
            )
        elif response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "alguns segundos")
            logger.warning(f"Throttling detectado (HTTP 429). Retry-After: {retry_after}")
            raise GraphAPIError(
                f"Limite de requisições excedido no Microsoft Graph (Throttling). Tente novamente em {retry_after}.",
                status_code=429,
                response_body=response.text,
            )
        else:
            logger.error(f"Erro na resposta HTTP ({response.status_code}): {response.text}")
            raise GraphAPIError(
                f"Erro na requisição ao Microsoft Graph ({response.status_code}): {response.text}",
                status_code=response.status_code,
                response_body=response.text,
            )

    def get(self, endpoint: str, token: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a GET request against an endpoint."""
        url = endpoint if endpoint.startswith("http") else f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = self._build_headers(token)
        self._apply_rate_limit()
        logger.debug(f"GET {url} (params: {params})")
        try:
            response = requests.get(url, headers=headers, params=params, timeout=self.timeout)
            return self._handle_response(response)
        except requests.RequestException as exc:
            if not isinstance(exc, GraphAPIError):
                logger.error(f"Falha de conexão com Microsoft Graph: {exc}", exc_info=True)
                raise GraphAPIError(f"Falha de conexão com Microsoft Graph: {exc}") from exc
            raise

    def get_paginated(
        self, endpoint: str, token: str, params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Fetch all pages of a collection following @odata.nextLink."""
        results: List[Dict[str, Any]] = []
        current_url = endpoint if endpoint.startswith("http") else f"{self.base_url}/{endpoint.lstrip('/')}"
        current_params = params

        while current_url:
            data = self.get(current_url, token, params=current_params)
            # Subsequent pages use the complete URL from nextLink, so params are not repeated
            current_params = None

            items = data.get("value", [])
            results.extend(items)
            current_url = data.get("@odata.nextLink")

        return results

    def get_notebooks(self, token: str) -> List[Dict[str, Any]]:
        """Retrieve all OneNote notebooks for the authenticated user."""
        return self.get_paginated("me/onenote/notebooks", token)

    def get_notebook(self, notebook_id: str, token: str) -> Dict[str, Any]:
        """Retrieve a specific notebook by ID."""
        return self.get(f"me/onenote/notebooks/{notebook_id}", token)

    def get_notebook_sections(self, notebook_id: str, token: str) -> List[Dict[str, Any]]:
        """Retrieve direct sections of a specific notebook."""
        return self.get_paginated(f"me/onenote/notebooks/{notebook_id}/sections", token)

    def get_notebook_section_groups(self, notebook_id: str, token: str) -> List[Dict[str, Any]]:
        """Retrieve direct section groups (subsections) of a specific notebook."""
        return self.get_paginated(f"me/onenote/notebooks/{notebook_id}/sectionGroups", token)

    def get_section_group_sections(self, section_group_id: str, token: str) -> List[Dict[str, Any]]:
        """Retrieve sections contained within a specific section group."""
        return self.get_paginated(f"me/onenote/sectionGroups/{section_group_id}/sections", token)

    def get_section_group_section_groups(self, section_group_id: str, token: str) -> List[Dict[str, Any]]:
        """Retrieve nested section groups contained within a specific section group."""
        return self.get_paginated(f"me/onenote/sectionGroups/{section_group_id}/sectionGroups", token)

    def get_section(self, section_id: str, token: str) -> Dict[str, Any]:
        """Retrieve a specific section by ID."""
        return self.get(f"me/onenote/sections/{section_id}", token)

    def get_section_pages(
        self,
        section_id: str,
        token: str,
        order_by: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve all pages of a specific section (including page levels)."""
        params: Dict[str, Any] = {"pagelevel": "true"}
        if order_by:
            params["$orderby"] = order_by
        return self.get_paginated(f"me/onenote/sections/{section_id}/pages", token, params=params)

    def get_page(self, page_id: str, token: str) -> Dict[str, Any]:
        """Retrieve a specific page metadata by ID."""
        return self.get(f"me/onenote/pages/{page_id}", token, params={"pagelevel": "true"})

    def get_page_content(
        self,
        page_id: str,
        token: str,
        include_ids: bool = True,
    ) -> str:
        """Fetch raw HTML/XHTML content of a OneNote page."""
        endpoint = f"me/onenote/pages/{page_id}/content"
        url = f"{self.base_url}/{endpoint}"
        headers = self._build_headers(token)
        headers["Accept"] = "text/html, application/xhtml+xml"
        params = {"includeIDs": "true"} if include_ids else None

        self._apply_rate_limit()
        try:
            response = requests.get(url, headers=headers, params=params, timeout=self.timeout)
            if response.status_code == 200:
                return response.text
            self._handle_response(response)
            return response.text
        except requests.RequestException as exc:
            if not isinstance(exc, GraphAPIError):
                raise GraphAPIError(f"Falha ao baixar conteúdo da página OneNote: {exc}") from exc
            raise

    def get_binary_resource(
        self,
        url_or_id: str,
        token: str,
    ) -> bytes:
        """Download binary content for an image or attachment resource."""
        if url_or_id.startswith("http://") or url_or_id.startswith("https://"):
            url = url_or_id
        else:
            resource_id = url_or_id.strip("/")
            url = f"{self.base_url}/me/onenote/resources/{resource_id}/$value"

        headers = self._build_headers(token)
        headers["Accept"] = "*/*"

        self._apply_rate_limit()
        try:
            response = requests.get(url, headers=headers, timeout=self.timeout * 2)
            if response.status_code == 200:
                return response.content
            self._handle_response(response)
            return response.content
        except requests.RequestException as exc:
            if not isinstance(exc, GraphAPIError):
                raise GraphAPIError(f"Falha ao baixar recurso binário ({url}): {exc}") from exc
            raise


