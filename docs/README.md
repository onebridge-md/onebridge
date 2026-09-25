# Documentação do OneBridge

Este diretório contém a arquitetura, planos de implantação e registros de validação (*walkthroughs*) de cada etapa do projeto **OneBridge**.

---

## 🏛️ Arquitetura Geral

- [**arquitetura.md**](arquitetura.md): Especificação técnica completa do sistema, princípios de Clean Architecture, fronteira de API, diagrama de camadas, fluxo de dados e convenções de diretórios.

---

## 📋 Planos e Walkthroughs por Etapa

| Etapa | Plano de Implantação | Walkthrough / Validação | Descrição |
| :--- | :--- | :--- | :--- |
| **01. Autenticação & Catálogo** | [01_plano_autenticacao.md](01_plano_autenticacao.md) | [01_walkthrough_listagem_notebooks.md](01_walkthrough_listagem_notebooks.md) | Camada OAuth 2.0 (MSAL + SQLite), fluxo de login/logout/status e comandos de listagem de cadernos. |
| **02. Exportação Markdown (`fetch-page`/`fetch-pages`)** | [02_plano_fetch_pages_markdown.md](02_plano_fetch_pages_markdown.md) | [02_walkthrough_fetch_pages_markdown.md](02_walkthrough_fetch_pages_markdown.md) | Comandos `fetch-page` e `fetch-pages`, conversor Markdown (GFM + frontmatter), pipeline de mídias (`IMAGENS/`) e anexos (`ANEXOS/`). |
| **03. Sistema de Logging** | [03_plano_logging.md](03_plano_logging.md) | [03_walkthrough_logging.md](03_walkthrough_logging.md) | Infraestrutura centralizada de logging (`LOGS/onebridge.log`), formato padronizado, níveis configuráveis e saída de erros para `STDERR`. |
| **04. Interface TUI (Textual)** | [arquitetura.md](arquitetura.md) | [04_walkthrough_tui.md](04_walkthrough_tui.md) | Interface interativa de terminal com navegação Vim (`h/j/k/l`), checkboxes, carregamento assíncrono e painel de progresso. |

