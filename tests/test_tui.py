"""Automated unit and integration tests for OneBridge TUI."""

import asyncio
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from onebridge.api.dto import (
    NotebookDTO,
    NotebookTreeDTO,
    PageDTO,
    PageExportResultDTO,
    SectionDTO,
    SectionGroupDTO,
)
from onebridge.cli.main import cli
from onebridge.tui.app import OneBridgeTUIApp
from onebridge.tui.screens.main import MainScreen
from onebridge.tui.widgets.progress_panel import ProgressPanel
from onebridge.tui.widgets.tree_browser import NodeData, TreeBrowser


def test_cli_tui_command_help():
    """Verify 'onebridge tui --help' is registered and runnable."""
    runner = CliRunner()
    result = runner.invoke(cli, ["tui", "--help"])
    assert result.exit_code == 0
    assert "Inicia a interface interativa de terminal (TUI)" in result.output
    assert "--client-id" in result.output
    assert "--authority" in result.output
    assert "--db-path" in result.output


def test_tree_browser_node_data_and_label_formatting():
    """Test TreeBrowser node creation and Rich label formatting."""
    tree = TreeBrowser("Test Tree")
    nb_dto = NotebookDTO(id="nb-1", name="Meu Caderno")
    node = tree.add_notebook_node(nb_dto)

    assert node.data.node_type == "notebook"
    assert node.data.id == "nb-1"
    assert node.data.name == "Meu Caderno"
    assert not node.data.checked

    label_text = tree.format_node_label(node.data).plain
    assert "[ ]" in label_text
    assert "Meu Caderno" in label_text

    # Toggle check
    node.data.checked = True
    label_checked = tree.format_node_label(node.data).plain
    assert "[x]" in label_checked


def test_tree_browser_hierarchy_and_cascading_selection():
    """Test adding child nodes and cascading selection with space / toggle_check."""
    tree = TreeBrowser("Test Tree")
    nb = tree.add_notebook_node(NotebookDTO(id="nb-1", name="Caderno 1"))
    sec = tree.add_section_node(
        nb, SectionDTO(id="sec-1", name="Seção 1"), notebook_id="nb-1", notebook_name="Caderno 1"
    )
    p1 = tree.add_page_node(
        sec,
        PageDTO(id="page-1", title="Nota 1"),
        notebook_id="nb-1",
        notebook_name="Caderno 1",
        section_id="sec-1",
        section_name="Seção 1",
    )
    p2 = tree.add_page_node(
        sec,
        PageDTO(id="page-2", title="Nota 2"),
        notebook_id="nb-1",
        notebook_name="Caderno 1",
        section_id="sec-1",
        section_name="Seção 1",
    )

    assert tree.count_selected() == 0

    # Select notebook node as cursor and toggle check
    tree.select_node(nb)
    tree.action_toggle_check()

    assert nb.data.checked is True
    assert sec.data.checked is True
    assert p1.data.checked is True
    assert p2.data.checked is True
    assert tree.count_selected() == 4

    targets = tree.get_selected_targets()
    target_ids = [t.id for t in targets]
    assert "nb-1" in target_ids
    assert "sec-1" in target_ids
    assert "page-1" in target_ids
    assert "page-2" in target_ids

    # Uncheck section
    tree.select_node(sec)
    tree.action_toggle_check()
    assert sec.data.checked is False
    assert p1.data.checked is False
    assert p2.data.checked is False


def test_tree_browser_vim_navigation_actions():
    """Test Vim key navigation handlers (h, l, a)."""
    tree = TreeBrowser("Test Tree")
    nb1 = tree.add_notebook_node(NotebookDTO(id="nb-1", name="Caderno 1"))
    sec1 = tree.add_section_node(
        nb1, SectionDTO(id="sec-1", name="Seção 1"), notebook_id="nb-1", notebook_name="Caderno 1"
    )

    # Test toggle_all ('a')
    tree.action_toggle_all()
    assert nb1.data.checked is True
    assert sec1.data.checked is True

    tree.action_toggle_all()
    assert nb1.data.checked is False
    assert sec1.data.checked is False

    # Test 'l' (expand_or_child)
    tree.select_node(nb1)
    nb1.collapse()
    assert not nb1.is_expanded
    tree.action_expand_or_child()
    assert nb1.is_expanded

    # Test 'h' (collapse_or_parent)
    tree.action_collapse_or_parent()
    assert not nb1.is_expanded


def test_progress_panel_workflow():
    """Test ProgressPanel metrics updating and task completion."""
    panel = ProgressPanel()

    async def _run():
        from textual.app import App, ComposeResult

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield panel

        app = TestApp()
        async with app.run_test() as pilot:
            panel.start_job(total=3, title="Exportando Teste")
            assert panel.total_pages == 3
            assert panel.exported_pages == 0

            panel.advance_page("Página 1", images_count=2, attachments_count=1, file_path="ARQUIVOS/p1.md")
            assert panel.exported_pages == 1
            assert panel.total_images == 2
            assert panel.total_attachments == 1

            panel.advance_page("Página 2", images_count=1, attachments_count=0, file_path="ARQUIVOS/p2.md")
            assert panel.exported_pages == 2
            assert panel.total_images == 3
            assert panel.total_attachments == 1

            panel.finish_job(success=True, message="Sucesso total!")
            await pilot.pause()

    asyncio.run(_run())


def test_tui_app_mount_and_refresh():
    """Test full TUI application mounting with mock API in headless mode."""
    mock_api = MagicMock()
    mock_api.is_authenticated.return_value = True
    mock_api.list_notebooks.return_value = [
        NotebookDTO(id="nb-test-1", name="Meu Caderno TUI"),
        NotebookDTO(id="nb-test-2", name="Caderno Secundário"),
    ]

    app = OneBridgeTUIApp(api=mock_api)

    async def _run():
        async with app.run_test() as pilot:
            await pilot.pause()
            main_screen = app.screen
            assert isinstance(main_screen, MainScreen)

            tree = main_screen.query_one("#tree_browser", TreeBrowser)
            assert tree is not None

            # Check action refresh
            main_screen.action_refresh_tree()
            await pilot.pause()

    asyncio.run(_run())


def test_tui_login_modal():
    """Test LoginModal display and interactions."""
    from onebridge.tui.screens.login import LoginModal

    mock_api = MagicMock()
    mock_api.is_authenticated.return_value = False

    modal = LoginModal(mock_api)

    async def _run():
        from textual.app import App, ComposeResult

        class TestApp(App):
            def on_mount(self):
                self.push_screen(modal)

        app = TestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            btn_close = modal.query_one("#btn_close")
            assert btn_close is not None
            # Press close
            modal.on_button_pressed(MagicMock(button=btn_close))
            await pilot.pause()

    asyncio.run(_run())


def test_tree_browser_loading_state_and_spinner():
    """Verify TreeBrowser loading state, hourglass icon, and spinner frames."""
    tree = TreeBrowser("Test Tree")
    nb = tree.add_notebook_node(NotebookDTO(id="nb-1", name="Meu Caderno"))

    assert not nb.data.loading
    assert "⏳" not in tree.format_node_label(nb.data).plain

    # Start loading
    tree.set_node_loading(nb, True, "Buscando seções no OneNote...")
    assert nb.data.loading is True
    assert tree.has_loading_nodes is True

    # Check parent label contains hourglass and spinner
    parent_label = tree.format_node_label(nb.data, spinner_char="⠋").plain
    assert "⏳" in parent_label
    assert "⠋" in parent_label
    assert "Meu Caderno" in parent_label

    # Check child loading node exists
    assert len(nb.children) == 1
    child = nb.children[0]
    assert child.data.node_type == "loading"
    child_label = tree.format_node_label(child.data, spinner_char="⠋").plain
    assert "⏳" in child_label
    assert "⠋" in child_label
    assert "Buscando seções no OneNote..." in child_label

    # Advance spinner frame
    tree._tick_spinner()
    assert tree._spinner_frame == 1
    char2 = tree.SPINNER_FRAMES[1]
    assert char2 in tree.format_node_label(nb.data, spinner_char=char2).plain

    # Verify loading child is not selected or exported
    tree.select_node(nb)
    tree.action_toggle_check()
    assert nb.data.checked is True
    assert child.data.checked is False
    assert tree.count_selected() == 1
    targets = tree.get_selected_targets()
    assert len(targets) == 1
    assert targets[0].id == "nb-1"

    # Stop loading
    tree.set_node_loading(nb, False)
    assert nb.data.loading is False
    assert tree.has_loading_nodes is False
    assert len(nb.children) == 0
    clean_label = tree.format_node_label(nb.data).plain
    assert "⏳" not in clean_label


def test_main_screen_lazy_load_shows_spinner_and_populates():
    """Test MainScreen node expansion with spinner display and children populating."""
    mock_api = MagicMock()
    mock_api.is_authenticated.return_value = True
    mock_api.list_notebooks.return_value = [
        NotebookDTO(id="nb-test", name="Caderno Paulo"),
    ]
    mock_api.get_notebook_tree.return_value = NotebookTreeDTO(
        notebook=NotebookDTO(id="nb-test", name="Caderno Paulo"),
        sections=[SectionDTO(id="sec-1", name="Seção de Teste")],
        section_groups=[],
    )

    app = OneBridgeTUIApp(api=mock_api)

    async def _run():
        async with app.run_test() as pilot:
            await pilot.pause()
            main_screen = app.screen
            tree = main_screen.query_one("#tree_browser", TreeBrowser)
            assert len(tree.root.children) == 1

            nb_node = tree.root.children[0]
            assert nb_node.data.name == "Caderno Paulo"

            # Expand node
            tree.select_node(nb_node)
            tree.action_expand_or_child()

            # Wait for background thread to resolve
            for _ in range(10):
                await pilot.pause()
                if nb_node.data.loaded:
                    break

            assert nb_node.data.loaded is True
            assert nb_node.data.loading is False
            # Check section child was added
            assert len(nb_node.children) == 1
            sec_child = nb_node.children[0]
            assert sec_child.data.node_type == "section"
            assert sec_child.data.name == "Seção de Teste"

    asyncio.run(_run())


def test_error_modal_display_and_dismiss():
    """Test ErrorModal displays title, context, summary, and dismisses on button click."""
    from onebridge.tui.screens.error_modal import ErrorModal
    from textual.app import App

    modal = ErrorModal(
        title="Falha de Conexão",
        message="Read timed out (timeout=15s)",
        context="Carregando seções",
        log_path="LOGS/onebridge_tui_errors.log",
    )

    class TestApp(App):
        def on_mount(self):
            self.push_screen(modal)

    async def _run():
        app = TestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.screen == modal

            title_widget = modal.query_one("#error_title")
            assert "Falha de Conexão" in str(title_widget.render())

            context_widget = modal.query_one("#error_context")
            assert "Carregando seções" in str(context_widget.render())

            summary_widget = modal.query_one("#error_summary")
            assert "Read timed out" in str(summary_widget.render())

            btn_close = modal.query_one("#btn_close")
            btn_close.press()
            await pilot.pause()

            # Modal should have been dismissed
            assert app.screen != modal

    asyncio.run(_run())


def test_main_screen_api_error_shows_error_modal_and_logs(tmp_path):
    """Test that when API raises an error in lazy loading, ErrorModal is displayed and error is logged."""
    from onebridge.core.graph_client import GraphAPIError
    from onebridge.tui.screens.error_modal import ErrorModal

    error_log_file = tmp_path / "onebridge_tui_errors.log"

    mock_api = MagicMock()
    mock_api.is_authenticated.return_value = True
    mock_api.list_notebooks.return_value = [
        NotebookDTO(id="nb-err", name="Caderno com Erro"),
    ]
    # Simulate the exact GraphAPIError seen in the user's screenshot
    mock_api.get_notebook_tree.side_effect = GraphAPIError(
        "Falha de conexão com Microsoft Graph: HTTPSConnectionPool: Read timed out."
    )

    app = OneBridgeTUIApp(api=mock_api)

    async def _run():
        with patch("onebridge.logger.TUI_ERROR_LOG_PATH", error_log_file):
            async with app.run_test() as pilot:
                await pilot.pause()
                main_screen = app.screen
                assert isinstance(main_screen, MainScreen)
                tree = main_screen.query_one("#tree_browser", TreeBrowser)
                nb_node = tree.root.children[0]

                # Expand node to trigger error
                tree.select_node(nb_node)
                tree.action_expand_or_child()

                for _ in range(15):
                    await pilot.pause()
                    if isinstance(app.screen, ErrorModal):
                        break

                # Verify ErrorModal is displayed on top
                assert isinstance(app.screen, ErrorModal)
                error_modal = app.screen
                assert "Falha ao Carregar Itens" in error_modal.error_title
                assert "Read timed out" in error_modal.error_message

                # Verify error was logged to onebridge_tui_errors.log
                assert error_log_file.exists()
                log_content = error_log_file.read_text(encoding="utf-8")
                assert "=" * 80 in log_content
                assert "ERRO CAPTURADO NA TUI" in log_content
                assert "Read timed out" in log_content

                # Dismiss modal
                error_modal.dismiss()
                await pilot.pause()
                assert app.screen == main_screen

    asyncio.run(_run())


def test_export_complete_modal_display_and_dismiss():
    """Test ExportCompleteModal renders metrics, output path, and dismisses."""
    from onebridge.tui.screens.export_complete_modal import ExportCompleteModal
    from textual.app import App

    modal = ExportCompleteModal(
        total_pages=5,
        exported_pages=4,
        total_images=12,
        total_attachments=2,
        failed_pages=1,
        output_dir="/caminho/para/ARQUIVOS",
        duration_seconds=3.5,
    )

    class TestApp(App):
        def on_mount(self):
            self.push_screen(modal)

    async def _run():
        app = TestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.screen == modal

            title_widget = modal.query_one("#export_title")
            assert "Exportação Concluída" in str(title_widget.render())

            stats_widget = modal.query_one("#export_stats")
            stats_text = str(stats_widget.render())
            assert "4 de 5" in stats_text
            assert "12" in stats_text
            assert "2" in stats_text
            assert "1" in stats_text
            assert "3.5s" in stats_text

            dir_widget = modal.query_one("#export_dir_notice")
            assert "/caminho/para/ARQUIVOS" in str(dir_widget.render())

            btn_close = modal.query_one("#btn_close")
            btn_close.press()
            await pilot.pause()
            assert app.screen != modal

    asyncio.run(_run())


def test_progress_panel_prepare_and_live_updates():
    """Test ProgressPanel prepare_job, indeterminate mode, spinner ticks, failure recording and finish."""
    panel = ProgressPanel()

    async def _run():
        from textual.app import App, ComposeResult
        from textual.widgets import ProgressBar

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield panel

        app = TestApp()
        async with app.run_test() as pilot:
            # 1. Prepare job (indeterminate)
            panel.prepare_job("Buscando lista de páginas...")
            await pilot.pause()

            title = panel.query_one("#panel_title")
            assert "EM EXECUÇÃO" in str(title.render())

            status = panel.query_one("#progress_status")
            assert "Buscando lista de páginas..." in str(status.render())

            bar = panel.query_one("#progress_bar", ProgressBar)
            assert bar.total is None

            # 2. Advance spinner
            panel._tick_spinner()
            frame = panel.SPINNER_FRAMES[panel._spinner_frame]
            status_render = str(panel.query_one("#progress_status").render())
            assert frame in status_render

            # 3. Start job with concrete total
            panel.start_job(total=2, title="Exportando")
            assert panel.total_pages == 2
            assert bar.total == 2

            # 4. Advance page
            panel.advance_page("Página 1", images_count=3, attachments_count=1, file_path="ARQUIVOS/p1.md")
            assert panel.exported_pages == 1
            assert panel.total_images == 3
            assert panel.total_attachments == 1

            # 5. Record failure
            panel.record_failure("Página 2", "Graph timeout")
            assert panel.failed_pages == 1

            # 6. Finish job
            panel.finish_job(success=True, message="Processamento finalizado!")
            await pilot.pause()

            title_done = panel.query_one("#panel_title")
            assert "CONCLUÍDO" in str(title_done.render())
            assert panel._spinner_timer is None

    asyncio.run(_run())


def test_main_screen_export_flow_and_complete_modal(tmp_path):
    """Test full MainScreen export action: button state change, live progress, and modal display."""
    from onebridge.tui.screens.export_complete_modal import ExportCompleteModal

    mock_api = MagicMock()
    mock_api.is_authenticated.return_value = True
    page_mock = PageDTO(id="page-101", title="Minha Nota Exportada")
    mock_api.list_notebooks.return_value = [
        NotebookDTO(id="nb-exp", name="Caderno Exportável"),
    ]
    mock_api.get_notebook_tree.return_value = NotebookTreeDTO(
        notebook=NotebookDTO(id="nb-exp", name="Caderno Exportável"),
        sections=[SectionDTO(id="sec-exp", name="Seção Única")],
        section_groups=[],
    )
    mock_api.list_sections.return_value = [SectionDTO(id="sec-exp", name="Seção Única")]
    mock_api.list_pages.return_value = [page_mock]
    mock_api.fetch_page.return_value = PageExportResultDTO(
        page_id="page-101",
        title="Minha Nota Exportada",
        file_path=str(tmp_path / "Minha Nota Exportada.md"),
        relative_path="Minha Nota Exportada.md",
        notebook_name="Caderno Exportável",
        section_name="Seção Única",
        images_downloaded=2,
        attachments_downloaded=1,
    )

    app = OneBridgeTUIApp(api=mock_api)

    async def _run():
        async with app.run_test() as pilot:
            await pilot.pause()
            main_screen = app.screen
            assert isinstance(main_screen, MainScreen)
            tree = main_screen.query_one("#tree_browser", TreeBrowser)
            nb_node = tree.root.children[0]
            tree.select_node(nb_node)
            tree.action_toggle_check()
            assert nb_node.data.checked is True

            btn_export = main_screen.query_one("#btn_export")
            assert not btn_export.disabled
            assert btn_export.label == "Exportar Selecionados (e)"

            # Trigger export action
            main_screen.action_export_selected()
            assert main_screen.is_exporting is True
            assert btn_export.disabled is True
            assert "Exportando" in str(btn_export.label)

            # Wait for background worker to complete and modal to pop up
            for _ in range(25):
                await pilot.pause()
                if isinstance(app.screen, ExportCompleteModal):
                    break

            assert isinstance(app.screen, ExportCompleteModal)
            complete_modal = app.screen
            assert complete_modal.exported_pages == 1
            assert complete_modal.total_images == 2
            assert complete_modal.total_attachments == 1

            # Dismiss modal
            complete_modal.dismiss()
            await pilot.pause()

            # Verify screen returned and export state reset
            assert app.screen == main_screen
            assert main_screen.is_exporting is False
            assert not btn_export.disabled
            assert btn_export.label == "Exportar Selecionados (e)"

    asyncio.run(_run())


def test_main_screen_section_group_lazy_load_and_children():
    """Verify expanding a section_group node loads child sections and subgroups without AttributeError."""
    from onebridge.tui.screens.error_modal import ErrorModal

    mock_api = MagicMock()
    mock_api.is_authenticated.return_value = True
    mock_api.list_notebooks.return_value = [
        NotebookDTO(id="nb-1", name="Meu Caderno de Culinária"),
    ]
    mock_api.get_notebook_tree.return_value = NotebookTreeDTO(
        notebook=NotebookDTO(id="nb-1", name="Meu Caderno de Culinária"),
        sections=[],
        section_groups=[SectionGroupDTO(id="sg-rec", name="RECEITAS")],
    )
    mock_api.list_section_group_sections.return_value = [
        SectionDTO(id="sec-bolo", name="Bolo de Cenoura"),
    ]
    mock_api.list_section_group_section_groups.return_value = [
        SectionGroupDTO(id="sg-doces", name="DOCES"),
    ]

    app = OneBridgeTUIApp(api=mock_api)

    async def _run():
        async with app.run_test() as pilot:
            await pilot.pause()
            main_screen = app.screen
            assert isinstance(main_screen, MainScreen)
            tree = main_screen.query_one("#tree_browser", TreeBrowser)
            nb_node = tree.root.children[0]

            # 1. Expand notebook
            tree.select_node(nb_node)
            tree.action_expand_or_child()

            for _ in range(10):
                await pilot.pause()
                if nb_node.data.loaded:
                    break

            assert nb_node.data.loaded is True
            assert len(nb_node.children) == 1
            sg_node = nb_node.children[0]
            assert sg_node.data.node_type == "section_group"
            assert sg_node.data.name == "RECEITAS"

            # 2. Expand section group 'RECEITAS'
            tree.select_node(sg_node)
            tree.action_expand_or_child()

            for _ in range(10):
                await pilot.pause()
                if sg_node.data.loaded:
                    break

            # Must NOT display ErrorModal!
            assert not isinstance(app.screen, ErrorModal)
            assert sg_node.data.loaded is True
            assert sg_node.data.loading is False

            # Children should contain DOCES (group) and Bolo de Cenoura (section)
            child_names = [c.data.name for c in sg_node.children]
            assert "DOCES" in child_names
            assert "Bolo de Cenoura" in child_names

    asyncio.run(_run())


def test_progress_panel_task_listing_and_live_progress():
    """Test ProgressPanel task table listing, active status, spinner, and completion transitions."""
    from onebridge.tui.widgets.progress_panel import ExportTask
    from textual.app import App, ComposeResult
    from textual.widgets import DataTable

    panel = ProgressPanel()

    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield panel

    async def _run():
        app = TestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            table = panel.query_one("#tasks_table", DataTable)
            assert len(table.rows) == 0

            # 1. Set tasks list
            t1 = ExportTask(id="task-1", page_id="p1", title="Primeira Página", notebook_name="Caderno A", section_name="Seção 1")
            t2 = ExportTask(id="task-2", page_id="p2", title="Segunda Página", notebook_name="Caderno A", section_name="Seção 1")
            panel.set_tasks([t1, t2])
            await pilot.pause()

            assert len(table.rows) == 2
            row_1 = table.get_row("task-1")
            assert "Na fila" in str(row_1[0])
            assert row_1[1] == "Primeira Página"
            assert "Caderno A / Seção 1" in str(row_1[2])

            # 2. Start task 1
            panel.start_task("task-1")
            await pilot.pause()
            assert panel._active_task_id == "task-1"
            row_1_active = table.get_row("task-1")
            assert "Ativa" in str(row_1_active[0])
            assert "Baixando" in str(row_1_active[3])

            # 3. Advance spinner frame
            panel._tick_spinner()
            await pilot.pause()
            frame = panel.SPINNER_FRAMES[panel._spinner_frame]
            row_1_spin = table.get_row("task-1")
            assert frame in str(row_1_spin[0])

            # 4. Complete task 1
            panel.complete_task("task-1", images_count=3, attachments_count=1, file_path="ARQUIVOS/p1.md")
            await pilot.pause()
            assert panel._active_task_id is None
            row_1_done = table.get_row("task-1")
            assert "Concluído" in str(row_1_done[0])
            assert "3 img" in str(row_1_done[3])

            # 5. Start task 2 and fail it
            panel.start_task("task-2")
            panel.fail_task("task-2", "Graph timeout")
            await pilot.pause()
            row_2_fail = table.get_row("task-2")
            assert "Falha" in str(row_2_fail[0])
            assert "Graph timeout" in str(row_2_fail[3])

            # 6. Add new tasks to queue
            t3 = ExportTask(id="task-3", page_id="p3", title="Terceira Página", notebook_name="Caderno B", section_name="Geral")
            panel.add_tasks([t3])
            await pilot.pause()
            assert len(table.rows) == 3
            row_3 = table.get_row("task-3")
            assert "Na fila" in str(row_3[0])

            # 7. Complete task 3 and finish job
            panel.complete_task("task-3")
            panel.finish_job(success=True)
            await pilot.pause()

            title_widget = panel.query_one("#panel_title")
            assert "CONCLUÍDO" in str(title_widget.render())

    asyncio.run(_run())


def test_main_screen_export_populates_tasks_table(tmp_path):
    """Test that MainScreen export populates tasks table and tracks active progress in real time."""
    from onebridge.tui.screens.export_complete_modal import ExportCompleteModal
    from textual.widgets import DataTable

    mock_api = MagicMock()
    mock_api.is_authenticated.return_value = True
    p1 = PageDTO(id="p-1", title="Nota Alfa", parent_section_name="Seção Alfa")
    p2 = PageDTO(id="p-2", title="Nota Beta", parent_section_name="Seção Beta")

    mock_api.list_notebooks.return_value = [NotebookDTO(id="nb-1", name="Caderno Teste")]
    mock_api.get_notebook_tree.return_value = NotebookTreeDTO(
        notebook=NotebookDTO(id="nb-1", name="Caderno Teste"),
        sections=[SectionDTO(id="sec-1", name="Seção Alfa")],
        section_groups=[],
    )
    mock_api.list_sections.return_value = [SectionDTO(id="sec-1", name="Seção Alfa")]
    mock_api.list_pages.return_value = [p1, p2]
    mock_api.fetch_page.return_value = PageExportResultDTO(
        page_id="p-1",
        title="Nota Alfa",
        file_path=str(tmp_path / "Nota Alfa.md"),
        relative_path="Nota Alfa.md",
        notebook_name="Caderno Teste",
        section_name="Seção Alfa",
        images_downloaded=1,
        attachments_downloaded=0,
    )

    app = OneBridgeTUIApp(api=mock_api)

    async def _run():
        async with app.run_test() as pilot:
            await pilot.pause()
            main_screen = app.screen
            assert isinstance(main_screen, MainScreen)
            tree = main_screen.query_one("#tree_browser", TreeBrowser)
            nb_node = tree.root.children[0]
            tree.select_node(nb_node)
            tree.action_toggle_check()

            # Trigger export
            main_screen.action_export_selected()

            # Wait for tasks to populate and execute
            progress_panel = main_screen.query_one("#progress_panel", ProgressPanel)
            tasks_table = progress_panel.query_one("#tasks_table", DataTable)

            for _ in range(30):
                await pilot.pause()
                if isinstance(app.screen, ExportCompleteModal):
                    break

            assert isinstance(app.screen, ExportCompleteModal)
            modal = app.screen
            assert modal.exported_pages == 2

            # Check tasks_table had both tasks recorded
            assert len(tasks_table.rows) == 2
            row_p1 = tasks_table.get_row("task-p-1")
            assert "Concluído" in str(row_p1[0])
            assert "Nota Alfa" in str(row_p1[1])

            modal.dismiss()
            await pilot.pause()

    asyncio.run(_run())






