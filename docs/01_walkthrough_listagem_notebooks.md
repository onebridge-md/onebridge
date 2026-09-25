# Walkthrough: Listagem de Notebooks no OneBridge

Implementamos a funcionalidade completa de consulta e listagem de cadernos (Notebooks) do Microsoft OneNote, integrando a validação e renovação de autenticação OAuth 2.0 e respeitando a arquitetura em camadas do projeto.

---

## 1. O que foi implementado

### 1.1. Camada de Domínio / Infraestrutura (`core/`)
- [`OneNoteGraphClient`](file:///home/pbal/development/onebridge/src/onebridge/core/graph_client.py):
  - Cliente HTTP com autenticação Bearer para o Microsoft Graph (`/me/onenote/notebooks`).
  - Suporte automático a paginação (`@odata.nextLink`).
  - Tratamento de exceções específicas: `GraphAuthError` (401/403), `GraphNotFoundError` (404), `GraphAPIError` (429 rate limit, 5xx).

### 1.2. Camada de DTOs e Contratos (`api/`)
- [`NotebookDTO`](file:///home/pbal/development/onebridge/src/onebridge/api/dto.py):
  - Modelo tipado contendo `id`, `name`, `created_at`, `modified_at`, `is_default`, `user_role`, `is_shared`, `web_url`, `client_url`, `sections_url`.
  - Construtor `from_graph_dict()` e serializador `to_dict()`.
- [`UserProfileDTO`](file:///home/pbal/development/onebridge/src/onebridge/api/dto.py):
  - Informações de perfil do usuário conectado.

### 1.3. Camada de Serviços (`services/`)
- [`CatalogService`](file:///home/pbal/development/onebridge/src/onebridge/services/catalog_service.py):
  - Métodos `list_notebooks()` e `get_notebook()`.
  - Suporte a ordenação por `modified`, `name` e `created`.

### 1.4. Camada de API Façade (`api/`)
- [`OneBridgeAPI`](file:///home/pbal/development/onebridge/src/onebridge/api/client.py):
  - Fronteira pública consumida pelas UIs (CLI / TUI).
  - Garante a presença e renovação silenciosa do token via [`OneNoteAuthenticator`](file:///home/pbal/development/onebridge/src/onebridge/auth/client.py).

### 1.5. Interface CLI (`cli/`)
- Comandos adicionados em [`main.py`](file:///home/pbal/development/onebridge/src/onebridge/cli/main.py):
  - `onebridge list-notebooks` (Comando padrão)
  - `onebridge list_notebooks` (Alias)
  - `onebridge notebooks` (Alias)
  - Opções: `--json`, `--format [table|json|csv|plain]`, `--sort-by [modified|name|created]`, `--db-path`.

---

## 2. Exemplos de Uso no Terminal

```bash
# Listagem formatada em tabela
onebridge list-notebooks

# Usando o alias alternativo
onebridge list_notebooks

# Exportar saída em JSON puro
onebridge list-notebooks --json

# Exportar em CSV
onebridge list-notebooks --format csv

# Ordenar por nome
onebridge list-notebooks --sort-by name
```

---

## 3. Validação e Testes Automatizados

Todos os 23 testes unitários e de integração passaram:

```bash
uv run --with pytest pytest
```
