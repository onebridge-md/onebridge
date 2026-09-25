# Walkthrough: Implementação da Interface TUI com Textual

Concluímos a implementação da **TUI (Terminal User Interface)** interativa do **OneBridge**, em conformidade com as diretrizes de [arquitetura.md](arquitetura.md) e utilizando o framework reativo **Textual**.

---

## 1. O Que Foi Implementado

### 1.1. Dependências e Configuração
- [`pyproject.toml`](../pyproject.toml) & [`requirements.txt`](../requirements.txt): Adicionada dependência `textual>=0.70.0`.
- Sincronização e instalação determinística com `uv`.

### 1.2. Módulo TUI (`src/onebridge/tui/`)
- **`TreeBrowser`** ([`src/onebridge/tui/widgets/tree_browser.py`](../src/onebridge/tui/widgets/tree_browser.py)):
  - Árvore interativa de cadernos, grupos de seções, seções e páginas com *lazy loading* assíncrono.
  - **Navegação Vim-style**:
    - `j`: Mover cursor para baixo.
    - `k`: Mover cursor para cima.
    - `h`: Fechar nó expandido ou subir para o nó pai.
    - `l`: Expandir nó ou descer para o primeiro filho.
  - **Seleção Múltipla com Checkboxes**:
    - `Espaço`: Alterna o estado `[x]` / `[ ]` do item em foco e propaga recursivamente para os nós filhos.
    - `a`: Alterna seleção de todos os itens da árvore.
  - **Indicador de Carregamento com Ampulheta e Spinning Wheel**:
    - Ao abrir um nó (caderno, grupo ou seção), a TUI exibe feedback visual imediato na linha pai (`[ ] 📓 Nome  ⏳ ⠋`) e insere um nó filho temporário (`   ⏳ ⠋ Buscando seções e grupos no OneNote...`).
    - Animação contínua do spinner (`⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏`) a cada 100ms em segundo plano sem travar a navegação.
    - Atualização do título do explorador (`📂 Explorador OneNote ⏳ ⠋ ...`) e do painel de detalhes (`Status: ⏳ Buscando dados...`).
    - Tratamento de nós vazios (`• (Nenhuma seção encontrada)`) e erros com remoção automática do indicador ao concluir.
  - Formatação visual rica com ícones (`📓`, `📁`, `📑`, `📄`) e destaques de cor.

- **`ProgressPanel`** ([`src/onebridge/tui/widgets/progress_panel.py`](../src/onebridge/tui/widgets/progress_panel.py)):
  - **Visualização em Abas (`TabbedContent`)**:
    - **Aba `📋 Tarefas`**: Tabela interativa (`DataTable`) com zebra stripes listando individualmente todas as tarefas de exportação em andamento ou enfileiradas.
      - Colunas: `Status`, `Tarefa / Página`, `Origem`, `Progresso / Detalhes`.
      - Estados visuais em tempo real: `⏳ Na fila`, `⏳ ⠋ Ativa` (com spinning wheel sincronizado na célula da tarefa em execução), `✔ Concluído` e `✖ Falha`.
      - Exibição de contexto de origem (`Notebook > Seção`) e caminho salvo / falha.
    - **Aba `📜 Log Detalhado`**: Log de eventos em tempo real com formatação Rich (`RichLog`) e rolagem automática (`auto_scroll=True`).
  - Barra de progresso reativa (`ProgressBar`) com suporte a modo indeterminado pulsante e modo com percentual fixo.
  - Indicador animado de spinning wheel (`⏳ ⠋ ...`) durante levantamento de páginas e exportação.
  - Destaque dinâmico no título do painel (`[⏳ EM EXECUÇÃO]` e `[✔ CONCLUÍDO]`) e no cabeçalho da aba de tarefas (`Tarefas (X/Y)`).
  - Badges de métricas em tempo real (`Páginas: X/Y`, `Imagens: N`, `Anexos: M`, e contagem de falhas).

- **Telas**:
  - `LoginModal` ([`src/onebridge/tui/screens/login.py`](../src/onebridge/tui/screens/login.py)): Modal para visualização de status da sessão e autenticação via *Device Code Flow* ou navegador local.
  - `ErrorModal` ([`src/onebridge/tui/screens/error_modal.py`](../src/onebridge/tui/screens/error_modal.py)): Caixa modal para exibição amigável do resumo de erros (ex: timeouts de rede, falhas de conexão à Graph API) com foco protegido, sem quebrar a tela da TUI, e indicando o caminho do log técnico.
  - `ExportCompleteModal` ([`src/onebridge/tui/screens/export_complete_modal.py`](../src/onebridge/tui/screens/export_complete_modal.py)): Caixa modal de confirmação exibida ao finalizar a exportação (`e`), apresentando resumo estruturado de páginas salvas, imagens extraídas, anexos baixados, eventuais falhas, tempo de execução e diretório de destino.
  - `MainScreen` ([`src/onebridge/tui/screens/main.py`](../src/onebridge/tui/screens/main.py)): Layout dividido em dois painéis (navegação à esquerda e detalhes/controles/progresso à direita), com execução de exportação assíncrona em worker thread, notificações de início/fim (`notify`), alerta sonoro (`bell`), desativação dinâmica do botão com contador (`⏳ Exportando (X/Y)...`), suporte a enfileiramento contínuo de novas tarefas de exportação se um trabalho já estiver ativo (`_pending_export_batches`) e restauração automática do estado.

- **Captura e Isolamento de Erros da TUI**:
  - Supressão de saída direta em `sys.stderr` durante a execução da TUI (`enable_stderr=False` e `TUIStderrCapture`), evitando que stack traces quebrem o buffer visual do terminal.
  - Gravação estruturada e persistente de todas as exceções da TUI em `LOGS/onebridge_tui_errors.log`, com timestamp claro (`[YYYY-MM-DD HH:MM:SS]`), separadores visuais (`=` e `-`), contexto da operação e stack trace completo.

- **Aplicação Principal**:
  - `OneBridgeTUIApp` ([`src/onebridge/tui/app.py`](../src/onebridge/tui/app.py)): Entrypoint da TUI com paleta visual moderna, captura de erros de workers e inicialização global de logs.

### 1.3. Integração CLI
- Novo comando `onebridge tui` adicionado em [`src/onebridge/cli/main.py`](../src/onebridge/cli/main.py), aceitando opções de autenticação (`--client-id`, `--authority`, `--db-path`).

---

## 2. Validação e Testes Automatizados

Foram criados testes automatizados cobrindo a navegação Vim, seleção em cascata, atualização de métricas, animação de loading/spinner, isolamento de `STDERR`, formato de log em `onebridge_tui_errors.log`, exibição e descarte do `ErrorModal` e ciclo de vida da aplicação Textual em modo headless ([`tests/test_tui.py`](../tests/test_tui.py) e [`tests/test_logger.py`](../tests/test_logger.py)):

```bash
uv run pytest
```

### Resultados dos Testes:
```text
============================= test session starts ==============================
collected 97 items

tests/test_api_client.py .....                                           [  5%]
tests/test_asset_pipeline.py .                                           [  6%]
tests/test_auth.py .......                                               [ 13%]
tests/test_catalog_service.py .....                                      [ 18%]
tests/test_cli.py ...                                                    [ 21%]
tests/test_cli_fetch.py ......                                           [ 27%]
tests/test_cli_notebooks.py .....                                        [ 32%]
tests/test_cli_pages.py .......                                          [ 40%]
tests/test_cli_sections.py ......                                        [ 46%]
tests/test_export_service.py ..                                          [ 48%]
tests/test_filesystem.py .......                                         [ 55%]
tests/test_graph_client.py ........                                      [ 63%]
tests/test_logger.py ...........                                         [ 75%]
tests/test_markdown_converter.py ....                                    [ 79%]
tests/test_settings.py ...                                               [ 82%]
tests/test_tui.py .................                                      [100%]

============================= 97 passed in 24.60s ==============================
```
