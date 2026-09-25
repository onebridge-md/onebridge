"""CLI interface for OneBridge Microsoft OneNote Access Layer."""

import csv
import io
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

import click

from onebridge import __version__
from onebridge.api.client import OneBridgeAPI
from onebridge.api.dto import (
    BatchExportResultDTO,
    NotebookDTO,
    NotebookTreeDTO,
    PageDTO,
    PageExportResultDTO,
    SectionDTO,
    SectionGroupDTO,
)
from onebridge.auth.client import OneNoteAuthenticator
from onebridge.config import (
    AUTHORITY,
    CLIENT_ID,
    DB_PATH,
    DEFAULT_EXPORT_DIR,
    DEFAULT_PLACEHOLDER_CLIENT_ID,
    DEFAULT_REQUEST_DELAY_MS,
)
from onebridge.core.graph_client import GraphAPIError
from onebridge.logger import get_logger, setup_logging

logger = get_logger("onebridge.cli.main")


@click.group()
@click.version_option(__version__, prog_name="onebridge")
def cli():
    """OneBridge - Camada de acesso e gerenciamento de notas do Microsoft OneNote."""
    setup_logging()


@cli.command("login")
@click.option(
    "--method",
    type=click.Choice(["device-code", "browser"], case_sensitive=False),
    default="device-code",
    help="Método de login: 'device-code' (padrão p/ terminal) ou 'browser' (abre navegador local).",
)
@click.option(
    "--client-id",
    default=None,
    help="Microsoft Entra (Azure) Application Client ID customizado.",
)
@click.option(
    "--authority",
    default=None,
    help="Authority URL (padrão: https://login.microsoftonline.com/common).",
)
@click.option(
    "--db-path",
    type=click.Path(dir_okay=False, writable=True, path_type=Path),
    default=DB_PATH,
    help="Caminho do arquivo SQLite para persistência dos tokens.",
)
def login_cmd(method: str, client_id: Optional[str], authority: Optional[str], db_path: Path):
    """Executa o ciclo de autenticação OAuth 2.0 e persiste os tokens no SQLite."""
    logger.info(f"Executando comando 'login' (método: {method})")
    auth = OneNoteAuthenticator(
        client_id=client_id,
        authority=authority,
        db_path=db_path,
    )

    # 1. Verifica se já existe uma sessão válida sem incomodar o usuário
    token_silencioso = auth.get_token_silently()
    if token_silencioso:
        click.secho("✅ Sessão já ativa e válida encontrada no cache SQLite!", fg="green")
        try:
            profile = auth.get_current_user_profile()
            name = profile.get("displayName", "N/A")
            email = profile.get("mail") or profile.get("userPrincipalName", "N/A")
            click.echo(f"👤 Usuário: {name} ({email})")
            logger.info(f"Login desnecessário: sessão já ativa para {name} ({email})")
            return
        except Exception:
            logger.warning("Falha ao recuperar perfil da sessão ativa. Revalidando credenciais...")
            click.secho("⚠️ Revalidando credenciais...", fg="yellow")

    if auth.client_id == DEFAULT_PLACEHOLDER_CLIENT_ID:
        click.secho(
            "ℹ️ Aviso: Usando Client ID padrão. Para contas pessoais Microsoft (@outlook, @hotmail),\n"
            "   é necessário registrar um Client ID próprio no Azure/Entra com suporte a contas pessoais.\n"
            "   (Configure via variável ONEBRIDGE_CLIENT_ID ou parâmetro --client-id)",
            fg="yellow",
        )

    click.echo(f"Iniciando autenticação com Microsoft Identity via [{method}]...")

    try:
        if method == "browser":
            auth.login_interactive()
        else:
            def print_instructions(message: str):
                click.echo("\n" + "=" * 60)
                click.secho(message, fg="cyan", bold=True)
                click.echo("=" * 60 + "\n")
                click.echo("Aguardando confirmação de autorização...")

            auth.login_device_flow(prompt_callback=print_instructions)

        click.secho("🎉 Login realizado com sucesso!", fg="green", bold=True)

        # Busca dados do usuário após login
        profile = auth.get_current_user_profile()
        name = profile.get("displayName", "N/A")
        email = profile.get("mail") or profile.get("userPrincipalName", "N/A")
        click.echo(f"👤 Conectado como: {name} ({email})")
        click.echo(f"💾 Sessão e Refresh Token salvos com segurança em: {db_path}")
        logger.info(f"Login concluído com sucesso para {name} ({email})")

    except Exception as e:
        logger.error(f"Erro durante o login: {e}", exc_info=True)
        click.secho(f"❌ Erro durante o login: {e}", fg="red", err=True)
        sys.exit(1)


@cli.command("status")
@click.option(
    "--client-id",
    default=None,
    help="Microsoft Entra (Azure) Application Client ID customizado.",
)
@click.option(
    "--authority",
    default=None,
    help="Authority URL.",
)
@click.option(
    "--db-path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=DB_PATH,
    help="Caminho do arquivo SQLite de autenticação.",
)
def status_cmd(client_id: Optional[str], authority: Optional[str], db_path: Path):
    """Verifica o status atual da autenticação e dados do usuário conectado."""
    logger.info("Executando comando 'status'")
    auth = OneNoteAuthenticator(client_id=client_id, authority=authority, db_path=db_path)
    metadata = auth.get_cached_metadata()

    if not metadata:
        logger.warning("Status: Nenhuma conta autenticada.")
        click.secho("❌ Nenhuma conta autenticada.", fg="red")
        click.echo("Execute 'onebridge login' para iniciar a sessão.")
        sys.exit(1)

    click.echo("🔎 Verificando validade da sessão...")
    token_silencioso = auth.get_token_silently()

    if not token_silencioso:
        logger.warning("Status: Sessão expirada ou revogada.")
        click.secho("⚠️ Sessão expirada ou revogada. É necessário fazer login novamente.", fg="yellow")
        click.echo("Execute 'onebridge login'.")
        sys.exit(1)

    try:
        profile = auth.get_current_user_profile()
        click.secho("✅ Autenticado com sucesso!", fg="green", bold=True)
        click.echo(f"👤 Nome:       {profile.get('displayName', 'N/A')}")
        click.echo(f"📧 E-mail:     {profile.get('mail') or profile.get('userPrincipalName', 'N/A')}")
        click.echo(f"🆔 ID:         {profile.get('id', 'N/A')}")
        click.echo(f"🔑 Client ID:  {auth.client_id}")
        click.echo(f"📅 Atualizado: {metadata.get('updated_at', 'N/A')}")
        click.echo(f"📁 Banco DB:   {db_path}")
        logger.info(f"Status verificado com sucesso para {profile.get('displayName')}")
    except Exception as e:
        logger.error(f"Erro ao consultar Microsoft Graph no status: {e}", exc_info=True)
        click.secho(f"⚠️ Erro ao consultar Microsoft Graph: {e}", fg="yellow")


@cli.command("logout")
@click.option(
    "--db-path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=DB_PATH,
    help="Caminho do arquivo SQLite de autenticação.",
)
def logout_cmd(db_path: Path):
    """Encerra a sessão ativa e remove os tokens do SQLite."""
    logger.info("Executando comando 'logout'")
    auth = OneNoteAuthenticator(db_path=db_path)
    auth.logout()
    click.secho("🚪 Sessão encerrada e tokens removidos com sucesso do SQLite.", fg="green")


def _format_date(iso_date: Optional[str]) -> str:
    """Format ISO timestamp for clean table display."""
    if not iso_date:
        return "-"
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso_date[:16]


def _render_notebooks_table(notebooks: List[NotebookDTO]) -> None:
    """Render a well-formatted console table with notebook items."""
    if not notebooks:
        click.secho("ℹ️ Nenhum caderno encontrado na sua conta OneNote.", fg="yellow")
        return

    click.echo("")
    click.secho(f"{'#':<3} {'NOME DO CADERNO':<30} {'ÚLTIMA MODIFICAÇÃO':<18} {'PADRÃO':<8} {'PAPEL':<10} {'ID'}", bold=True, fg="cyan")
    click.echo("-" * 95)

    for idx, nb in enumerate(notebooks, start=1):
        name = (nb.name[:27] + "...") if len(nb.name) > 30 else nb.name
        mod_date = _format_date(nb.modified_at)
        default_mark = "⭐ Sim" if nb.is_default else "Não"
        role = nb.user_role or "Owner"
        click.echo(f"{idx:<3} {name:<30} {mod_date:<18} {default_mark:<8} {role:<10} {nb.id}")

    click.echo("-" * 95)
    click.secho(f"📚 Total de cadernos: {len(notebooks)}", fg="green", bold=True)
    click.echo("")


def _render_notebooks_csv(notebooks: List[NotebookDTO]) -> None:
    """Render notebooks list as CSV."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "name", "created_at", "modified_at", "is_default", "user_role", "is_shared", "web_url", "client_url"])
    for nb in notebooks:
        writer.writerow([
            nb.id,
            nb.name,
            nb.created_at or "",
            nb.modified_at or "",
            nb.is_default,
            nb.user_role,
            nb.is_shared,
            nb.web_url or "",
            nb.client_url or "",
        ])
    click.echo(output.getvalue().strip())


def _render_notebooks_plain(notebooks: List[NotebookDTO]) -> None:
    """Render notebooks list in simple tab-delimited text."""
    for nb in notebooks:
        click.echo(f"{nb.id}\t{nb.name}\t{_format_date(nb.modified_at)}\t{nb.user_role}")


def _list_notebooks_action(
    fmt: str,
    as_json: bool,
    sort_by: str,
    client_id: Optional[str],
    authority: Optional[str],
    db_path: Path,
) -> None:
    """Core logic to fetch and display notebooks."""
    logger.info(f"Executando list-notebooks (fmt: {fmt}, sort_by: {sort_by})")
    api = OneBridgeAPI(client_id=client_id, authority=authority, db_path=db_path)
    reverse = False if sort_by == "name" else True

    try:
        notebooks = api.list_notebooks(sort_by=sort_by, reverse=reverse)
        logger.info(f"list-notebooks: {len(notebooks)} caderno(s) encontrado(s)")
    except RuntimeError as e:
        logger.error(f"Erro em list-notebooks: {e}", exc_info=True)
        click.secho(f"❌ {e}", fg="red", err=True)
        sys.exit(1)
    except GraphAPIError as e:
        logger.error(f"Erro ao consultar Microsoft Graph em list-notebooks: {e}", exc_info=True)
        click.secho(f"❌ Erro ao consultar Microsoft Graph: {e}", fg="red", err=True)
        sys.exit(1)

    # Format output
    if as_json or fmt == "json":
        data = [nb.to_dict() for nb in notebooks]
        click.echo(json.dumps(data, indent=2, ensure_ascii=False))
    elif fmt == "csv":
        _render_notebooks_csv(notebooks)
    elif fmt == "plain":
        _render_notebooks_plain(notebooks)
    else:
        _render_notebooks_table(notebooks)


@cli.command("list-notebooks")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "json", "csv", "plain"], case_sensitive=False),
    default="table",
    help="Formato de saída: 'table' (padrão), 'json', 'csv' ou 'plain'.",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Atalho para exibir a saída em formato JSON.",
)
@click.option(
    "--sort-by",
    type=click.Choice(["modified", "name", "created"], case_sensitive=False),
    default="modified",
    help="Critério de ordenação dos cadernos (padrão: 'modified').",
)
@click.option(
    "--client-id",
    default=None,
    help="Microsoft Entra (Azure) Application Client ID customizado.",
)
@click.option(
    "--authority",
    default=None,
    help="Authority URL.",
)
@click.option(
    "--db-path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=DB_PATH,
    help="Caminho do arquivo SQLite de autenticação.",
)
def list_notebooks_cmd(
    fmt: str,
    as_json: bool,
    sort_by: str,
    client_id: Optional[str],
    authority: Optional[str],
    db_path: Path,
):
    """Lista todos os cadernos (notebooks) disponíveis no OneNote do usuário."""
    _list_notebooks_action(
        fmt=fmt,
        as_json=as_json,
        sort_by=sort_by,
        client_id=client_id,
        authority=authority,
        db_path=db_path,
    )


@cli.command("list_notebooks", hidden=True)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "json", "csv", "plain"], case_sensitive=False),
    default="table",
)
@click.option("--json", "as_json", is_flag=True)
@click.option(
    "--sort-by",
    type=click.Choice(["modified", "name", "created"], case_sensitive=False),
    default="modified",
)
@click.option(
    "--client-id",
    default=None,
)
@click.option(
    "--authority",
    default=None,
)
@click.option(
    "--db-path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=DB_PATH,
)
def list_notebooks_alias_cmd(
    fmt: str,
    as_json: bool,
    sort_by: str,
    client_id: Optional[str],
    authority: Optional[str],
    db_path: Path,
):
    """Alias para 'list-notebooks'."""
    _list_notebooks_action(
        fmt=fmt,
        as_json=as_json,
        sort_by=sort_by,
        client_id=client_id,
        authority=authority,
        db_path=db_path,
    )


@cli.command("notebooks")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "json", "csv", "plain"], case_sensitive=False),
    default="table",
    help="Formato de saída: 'table' (padrão), 'json', 'csv' ou 'plain'.",
)
@click.option("--json", "as_json", is_flag=True, help="Atalho para formato JSON.")
@click.option(
    "--sort-by",
    type=click.Choice(["modified", "name", "created"], case_sensitive=False),
    default="modified",
    help="Critério de ordenação.",
)
@click.option(
    "--client-id",
    default=None,
    help="Microsoft Entra (Azure) Application Client ID customizado.",
)
@click.option(
    "--authority",
    default=None,
    help="Authority URL.",
)
@click.option(
    "--db-path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=DB_PATH,
    help="Caminho do banco SQLite.",
)
def notebooks_cmd(
    fmt: str,
    as_json: bool,
    sort_by: str,
    client_id: Optional[str],
    authority: Optional[str],
    db_path: Path,
):
    """Lista e consulta cadernos do OneNote."""
    _list_notebooks_action(
        fmt=fmt,
        as_json=as_json,
        sort_by=sort_by,
        client_id=client_id,
        authority=authority,
        db_path=db_path,
    )


def _render_sections_table(sections: List[SectionDTO]) -> None:
    """Render a well-formatted console table with section items."""
    if not sections:
        click.secho("ℹ️ Nenhuma seção encontrada para este caderno.", fg="yellow")
        return

    click.echo("")
    click.secho(
        f"{'#':<3} {'NOME DA SEÇÃO':<28} {'GRUPO / CAMINHO':<26} {'ÚLTIMA MODIFICAÇÃO':<18} {'PADRÃO':<8} {'ID'}",
        bold=True,
        fg="cyan",
    )
    click.echo("-" * 115)

    for idx, s in enumerate(sections, start=1):
        name = (s.name[:25] + "...") if len(s.name) > 28 else s.name
        parent = s.parent_path or "(Raiz)"
        parent_display = (parent[:23] + "...") if len(parent) > 26 else parent
        mod_date = _format_date(s.modified_at)
        default_mark = "⭐ Sim" if s.is_default else "Não"
        click.echo(
            f"{idx:<3} {name:<28} {parent_display:<26} {mod_date:<18} {default_mark:<8} {s.id}"
        )

    click.echo("-" * 115)
    click.secho(f"📑 Total de seções: {len(sections)}", fg="green", bold=True)
    click.echo("")


def _render_tree_recursive(
    section_groups: List[Any],
    sections: List[SectionDTO],
    prefix: str = "",
) -> None:
    """Helper to print tree lines for section groups and sections."""
    total_items = len(section_groups) + len(sections)
    current_idx = 0

    # 1. Direct sections in this level
    for s in sections:
        current_idx += 1
        is_last = current_idx == total_items
        connector = "└── " if is_last else "├── "
        default_badge = " [padrão]" if s.is_default else ""
        click.echo(f"{prefix}{connector}📄 {click.style(s.name, fg='green')}{default_badge} {click.style(f'({s.id})', dim=True)}")

    # 2. Section Groups (subsections)
    for sg in section_groups:
        current_idx += 1
        is_last = current_idx == total_items
        connector = "└── " if is_last else "├── "
        child_prefix = prefix + ("    " if is_last else "│   ")
        click.echo(f"{prefix}{connector}📁 {click.style(sg.name, fg='yellow', bold=True)} {click.style(f'({sg.id})', dim=True)}")

        # Recursively render inside this group
        _render_tree_recursive(
            section_groups=getattr(sg, "section_groups", []) or [],
            sections=getattr(sg, "sections", []) or [],
            prefix=child_prefix,
        )


def _render_sections_tree(tree: Any) -> None:
    """Render hierarchical tree display of notebook, section groups, and sections."""
    nb = tree.notebook
    click.echo("")
    click.secho(f"📓 {nb.name}", fg="blue", bold=True)
    click.secho(f"   ID: {nb.id}", dim=True)
    click.echo("")

    _render_tree_recursive(
        section_groups=tree.section_groups,
        sections=tree.sections,
        prefix="   ",
    )

    total_sections = len(tree.sections)
    def _count(groups):
        nonlocal total_sections
        for g in groups:
            total_sections += len(g.sections or [])
            _count(g.section_groups or [])
    _count(tree.section_groups)

    click.echo("")
    click.secho(f"📑 Total de seções na hierarquia: {total_sections}", fg="green", bold=True)
    click.echo("")


def _render_sections_csv(sections: List[SectionDTO]) -> None:
    """Render sections list as CSV."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id",
        "name",
        "parent_path",
        "created_at",
        "modified_at",
        "is_default",
        "parent_notebook_id",
        "parent_section_group_id",
        "web_url",
        "client_url",
    ])
    for s in sections:
        writer.writerow([
            s.id,
            s.name,
            s.parent_path or "",
            s.created_at or "",
            s.modified_at or "",
            s.is_default,
            s.parent_notebook_id or "",
            s.parent_section_group_id or "",
            s.web_url or "",
            s.client_url or "",
        ])
    click.echo(output.getvalue().strip())


def _render_sections_plain(sections: List[SectionDTO]) -> None:
    """Render sections list in simple tab-delimited text."""
    for s in sections:
        click.echo(f"{s.id}\t{s.name}\t{s.parent_path or ''}\t{_format_date(s.modified_at)}")


def _list_sections_action(
    notebook: str,
    fmt: str,
    as_json: bool,
    tree_mode: bool,
    direct_only: bool,
    sort_by: str,
    client_id: Optional[str],
    authority: Optional[str],
    db_path: Path,
) -> None:
    """Core logic to fetch and display sections."""
    logger.info(f"Executando list-sections (caderno: {notebook}, tree: {tree_mode}, direct_only: {direct_only})")
    api = OneBridgeAPI(client_id=client_id, authority=authority, db_path=db_path)

    # 1. Tree Mode handling
    if tree_mode or fmt == "tree":
        try:
            tree = api.get_notebook_tree(notebook=notebook)
            logger.info(f"list-sections (tree): árvore obtida para '{notebook}'")
        except RuntimeError as e:
            logger.error(f"Erro em list-sections: {e}", exc_info=True)
            click.secho(f"❌ {e}", fg="red", err=True)
            sys.exit(1)
        except GraphAPIError as e:
            logger.error(f"Erro ao consultar Microsoft Graph em list-sections: {e}", exc_info=True)
            click.secho(f"❌ Erro ao consultar Microsoft Graph: {e}", fg="red", err=True)
            sys.exit(1)

        if as_json or fmt == "json":
            click.echo(json.dumps(tree.to_dict(), indent=2, ensure_ascii=False))
        else:
            _render_sections_tree(tree)
        return

    # 2. List / Table / CSV / Plain Mode handling
    recursive = not direct_only
    reverse = False if sort_by in ("name", "path") else True

    try:
        sections = api.list_sections(
            notebook=notebook,
            recursive=recursive,
            sort_by=sort_by,
            reverse=reverse,
        )
        logger.info(f"list-sections: {len(sections)} seção(ões) encontrada(s)")
    except RuntimeError as e:
        logger.error(f"Erro em list-sections: {e}", exc_info=True)
        click.secho(f"❌ {e}", fg="red", err=True)
        sys.exit(1)
    except GraphAPIError as e:
        logger.error(f"Erro ao consultar Microsoft Graph em list-sections: {e}", exc_info=True)
        click.secho(f"❌ Erro ao consultar Microsoft Graph: {e}", fg="red", err=True)
        sys.exit(1)

    if as_json or fmt == "json":
        data = [s.to_dict() for s in sections]
        click.echo(json.dumps(data, indent=2, ensure_ascii=False))
    elif fmt == "csv":
        _render_sections_csv(sections)
    elif fmt == "plain":
        _render_sections_plain(sections)
    else:
        _render_sections_table(sections)


@cli.command("list-sections")
@click.argument("notebook", required=True)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "tree", "json", "csv", "plain"], case_sensitive=False),
    default="table",
    help="Formato de saída: 'table' (padrão), 'tree', 'json', 'csv' ou 'plain'.",
)
@click.option(
    "--tree",
    "tree_mode",
    is_flag=True,
    help="Atalho para exibir a estrutura completa em árvore hierárquica.",
)
@click.option(
    "--direct-only",
    "--no-recursive",
    "direct_only",
    is_flag=True,
    help="Lista apenas seções do nível raiz (ignora grupos de subseções aninhados).",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Atalho para formato JSON.",
)
@click.option(
    "--sort-by",
    type=click.Choice(["name", "modified", "created", "path"], case_sensitive=False),
    default="name",
    help="Critério de ordenação das seções (padrão: 'name').",
)
@click.option(
    "--client-id",
    default=None,
    help="Microsoft Entra (Azure) Application Client ID customizado.",
)
@click.option(
    "--authority",
    default=None,
    help="Authority URL.",
)
@click.option(
    "--db-path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=DB_PATH,
    help="Caminho do banco SQLite.",
)
def list_sections_cmd(
    notebook: str,
    fmt: str,
    tree_mode: bool,
    direct_only: bool,
    as_json: bool,
    sort_by: str,
    client_id: Optional[str],
    authority: Optional[str],
    db_path: Path,
):
    """Lista seções e subseções de um caderno (identificado por ID ou Nome)."""
    _list_sections_action(
        notebook=notebook,
        fmt=fmt,
        as_json=as_json,
        tree_mode=tree_mode,
        direct_only=direct_only,
        sort_by=sort_by,
        client_id=client_id,
        authority=authority,
        db_path=db_path,
    )


@cli.command("list_sections", hidden=True)
@click.argument("notebook", required=True)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "tree", "json", "csv", "plain"], case_sensitive=False),
    default="table",
)
@click.option("--tree", "tree_mode", is_flag=True)
@click.option("--direct-only", "--no-recursive", "direct_only", is_flag=True)
@click.option("--json", "as_json", is_flag=True)
@click.option(
    "--sort-by",
    type=click.Choice(["name", "modified", "created", "path"], case_sensitive=False),
    default="name",
)
@click.option("--client-id", default=None)
@click.option("--authority", default=None)
@click.option("--db-path", type=click.Path(dir_okay=False, path_type=Path), default=DB_PATH)
def list_sections_alias_cmd(
    notebook: str,
    fmt: str,
    tree_mode: bool,
    direct_only: bool,
    as_json: bool,
    sort_by: str,
    client_id: Optional[str],
    authority: Optional[str],
    db_path: Path,
):
    """Alias para 'list-sections'."""
    _list_sections_action(
        notebook=notebook,
        fmt=fmt,
        as_json=as_json,
        tree_mode=tree_mode,
        direct_only=direct_only,
        sort_by=sort_by,
        client_id=client_id,
        authority=authority,
        db_path=db_path,
    )


@cli.command("sections")
@click.argument("notebook", required=True)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "tree", "json", "csv", "plain"], case_sensitive=False),
    default="table",
    help="Formato de saída: 'table' (padrão), 'tree', 'json', 'csv' ou 'plain'.",
)
@click.option("--tree", "tree_mode", is_flag=True, help="Atalho para exibição em árvore.")
@click.option(
    "--direct-only",
    "--no-recursive",
    "direct_only",
    is_flag=True,
    help="Lista apenas seções do nível raiz.",
)
@click.option("--json", "as_json", is_flag=True, help="Atalho para formato JSON.")
@click.option(
    "--sort-by",
    type=click.Choice(["name", "modified", "created", "path"], case_sensitive=False),
    default="name",
    help="Critério de ordenação.",
)
@click.option("--client-id", default=None, help="Application Client ID.")
@click.option("--authority", default=None, help="Authority URL.")
@click.option(
    "--db-path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=DB_PATH,
    help="Caminho do banco SQLite.",
)
def sections_cmd(
    notebook: str,
    fmt: str,
    tree_mode: bool,
    direct_only: bool,
    as_json: bool,
    sort_by: str,
    client_id: Optional[str],
    authority: Optional[str],
    db_path: Path,
):
    """Lista e consulta seções de um caderno do OneNote."""
    _list_sections_action(
        notebook=notebook,
        fmt=fmt,
        as_json=as_json,
        tree_mode=tree_mode,
        direct_only=direct_only,
        sort_by=sort_by,
        client_id=client_id,
        authority=authority,
        db_path=db_path,
    )


def _render_pages_table(
    pages: List[PageDTO],
    section_title: Optional[str] = None,
    notebook_title: Optional[str] = None,
) -> None:
    """Render a well-formatted console table with page items."""
    if not pages:
        context_msg = f" para a seção '{section_title}'" if section_title else ""
        click.secho(f"ℹ️ Nenhuma página encontrada{context_msg}.", fg="yellow")
        return

    click.echo("")
    if notebook_title or section_title:
        if notebook_title:
            click.secho(f"📓 Caderno: {notebook_title}", fg="blue", bold=True)
        if section_title:
            click.secho(f"📑 Seção:   {section_title}", fg="cyan", bold=True)
        click.echo("")

    click.secho(
        f"{'#':<3} {'TÍTULO DA PÁGINA':<38} {'CRIADO EM':<16} {'ÚLTIMA MODIFICAÇÃO':<18} {'ID'}",
        bold=True,
        fg="cyan",
    )
    click.echo("-" * 115)

    for idx, p in enumerate(pages, start=1):
        indent = "  " * p.level
        prefix = "↳ " if p.level > 0 else ""
        raw_display = f"{indent}{prefix}{p.title}"
        title_display = (raw_display[:35] + "...") if len(raw_display) > 38 else raw_display
        created_date = _format_date(p.created_at)
        mod_date = _format_date(p.modified_at)
        click.echo(
            f"{idx:<3} {title_display:<38} {created_date:<16} {mod_date:<18} {p.id}"
        )

    click.echo("-" * 115)
    click.secho(f"📄 Total de páginas: {len(pages)}", fg="green", bold=True)
    click.echo("")


def _render_pages_csv(pages: List[PageDTO]) -> None:
    """Render pages list as CSV."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id",
        "title",
        "level",
        "order",
        "parent_section_id",
        "parent_section_name",
        "created_at",
        "modified_at",
        "content_url",
        "web_url",
        "client_url",
    ])
    for p in pages:
        writer.writerow([
            p.id,
            p.title,
            p.level,
            p.order,
            p.parent_section_id or "",
            p.parent_section_name or "",
            p.created_at or "",
            p.modified_at or "",
            p.content_url or "",
            p.web_url or "",
            p.client_url or "",
        ])
    click.echo(output.getvalue().strip())


def _render_pages_plain(pages: List[PageDTO]) -> None:
    """Render pages list in simple tab-delimited text."""
    for p in pages:
        click.echo(f"{p.id}\t{p.title}\t{p.level}\t{_format_date(p.modified_at)}")


def _list_pages_action(
    section: Optional[str],
    notebook: Optional[str],
    fmt: str,
    as_json: bool,
    sort_by: str,
    order_direction: Optional[str],
    client_id: Optional[str],
    authority: Optional[str],
    db_path: Path,
) -> None:
    """Core logic to fetch and display pages."""
    logger.info(f"Executando list-pages (seção: {section}, caderno: {notebook}, sort_by: {sort_by})")
    api = OneBridgeAPI(client_id=client_id, authority=authority, db_path=db_path)

    # Calculate reverse
    if order_direction == "desc":
        reverse = True
    elif order_direction == "asc":
        reverse = False
    else:
        # Default sort direction per sort field
        if sort_by in ("modified", "created"):
            reverse = True
        else:
            reverse = False

    try:
        pages = api.list_pages(
            section=section,
            notebook=notebook,
            sort_by=sort_by,
            reverse=reverse,
        )
        logger.info(f"list-pages: {len(pages)} página(s) encontrada(s)")
    except ValueError as e:
        logger.warning(f"list-pages aviso: {e}")
        click.secho(f"ℹ️ {e}", fg="yellow")
        sys.exit(1)
    except RuntimeError as e:
        logger.error(f"Erro em list-pages: {e}", exc_info=True)
        click.secho(f"❌ {e}", fg="red", err=True)
        sys.exit(1)
    except GraphAPIError as e:
        logger.error(f"Erro ao consultar Microsoft Graph em list-pages: {e}", exc_info=True)
        click.secho(f"❌ Erro ao consultar Microsoft Graph: {e}", fg="red", err=True)
        sys.exit(1)
    except Exception as e:
        logger.error(f"Erro inesperado em list-pages: {e}", exc_info=True)
        click.secho(f"❌ Erro: {e}", fg="red", err=True)
        sys.exit(1)

    if as_json or fmt == "json":
        data = [p.to_dict() for p in pages]
        click.echo(json.dumps(data, indent=2, ensure_ascii=False))
    elif fmt == "csv":
        _render_pages_csv(pages)
    elif fmt == "plain":
        _render_pages_plain(pages)
    else:
        sec_name = section
        nb_name = notebook
        if pages and pages[0].parent_section_name:
            sec_name = pages[0].parent_section_name
        if not sec_name:
            def_sec = api.get_defaults().get("section")
            if def_sec:
                sec_name = def_sec.get("name")
        if not nb_name:
            def_nb = api.get_defaults().get("notebook")
            if def_nb:
                nb_name = def_nb.get("name")
        _render_pages_table(pages, section_title=sec_name, notebook_title=nb_name)


@cli.command("set-notebook")
@click.argument("notebook", required=False, default=None)
@click.option("--show", is_flag=True, help="Exibe o caderno padrão atualmente configurado.")
@click.option("--clear", is_flag=True, help="Remove a configuração do caderno padrão.")
@click.option(
    "--client-id",
    default=None,
    help="Microsoft Entra (Azure) Application Client ID customizado.",
)
@click.option(
    "--authority",
    default=None,
    help="Authority URL.",
)
@click.option(
    "--db-path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=DB_PATH,
    help="Caminho do arquivo SQLite de autenticação/configurações.",
)
def set_notebook_cmd(
    notebook: Optional[str],
    show: bool,
    clear: bool,
    client_id: Optional[str],
    authority: Optional[str],
    db_path: Path,
):
    """Define ou consulta o caderno (notebook) padrão para comandos subsequentes."""
    logger.info(f"Executando set-notebook (notebook: {notebook}, show: {show}, clear: {clear})")
    api = OneBridgeAPI(client_id=client_id, authority=authority, db_path=db_path)
    if clear:
        api.clear_defaults("notebook")
        logger.info("Configuração de caderno padrão removida.")
        click.secho("🗑️ Configuração de caderno padrão removida com sucesso.", fg="green")
        return

    if show or not notebook:
        defaults = api.get_defaults()
        def_nb = defaults.get("notebook")
        if def_nb and (def_nb.get("name") or def_nb.get("id")):
            click.echo(
                f"📓 Caderno padrão atual: {click.style(def_nb.get('name', 'N/A'), bold=True)} ({def_nb.get('id', 'N/A')})"
            )
        else:
            click.secho("ℹ️ Nenhum caderno padrão configurado no momento.", fg="yellow")
            click.echo("Use 'onebridge set-notebook <nome_ou_id>' para configurar.")
        return

    try:
        nb = api.set_default_notebook(notebook=notebook)
        logger.info(f"Caderno padrão definido: {nb.name} ({nb.id})")
        click.secho("⭐ Caderno padrão configurado com sucesso!", fg="green", bold=True)
        click.echo(f"📓 Nome: {nb.name}")
        click.echo(f"🆔 ID:   {nb.id}")
    except RuntimeError as e:
        logger.error(f"Erro em set-notebook: {e}", exc_info=True)
        click.secho(f"❌ {e}", fg="red", err=True)
        sys.exit(1)
    except GraphAPIError as e:
        logger.error(f"Erro ao consultar Microsoft Graph em set-notebook: {e}", exc_info=True)
        click.secho(f"❌ Erro ao consultar Microsoft Graph: {e}", fg="red", err=True)
        sys.exit(1)
    except Exception as e:
        logger.error(f"Erro em set-notebook: {e}", exc_info=True)
        click.secho(f"❌ Erro: {e}", fg="red", err=True)
        sys.exit(1)


@cli.command("set-section")
@click.argument("section", required=False, default=None)
@click.option(
    "--notebook",
    "-n",
    default=None,
    help="Caderno no qual a seção está localizada (opcional).",
)
@click.option("--show", is_flag=True, help="Exibe a seção padrão atualmente configurada.")
@click.option("--clear", is_flag=True, help="Remove a configuração da seção padrão.")
@click.option(
    "--client-id",
    default=None,
    help="Microsoft Entra (Azure) Application Client ID customizado.",
)
@click.option(
    "--authority",
    default=None,
    help="Authority URL.",
)
@click.option(
    "--db-path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=DB_PATH,
    help="Caminho do arquivo SQLite de autenticação/configurações.",
)
def set_section_cmd(
    section: Optional[str],
    notebook: Optional[str],
    show: bool,
    clear: bool,
    client_id: Optional[str],
    authority: Optional[str],
    db_path: Path,
):
    """Define ou consulta a seção padrão para comandos subsequentes."""
    logger.info(f"Executando set-section (seção: {section}, caderno: {notebook}, show: {show}, clear: {clear})")
    api = OneBridgeAPI(client_id=client_id, authority=authority, db_path=db_path)
    if clear:
        api.clear_defaults("section")
        logger.info("Configuração de seção padrão removida.")
        click.secho("🗑️ Configuração de seção padrão removida com sucesso.", fg="green")
        return

    if show or not section:
        defaults = api.get_defaults()
        def_sec = defaults.get("section")
        if def_sec and (def_sec.get("name") or def_sec.get("id")):
            click.echo(
                f"📑 Seção padrão atual: {click.style(def_sec.get('name', 'N/A'), bold=True)} ({def_sec.get('id', 'N/A')})"
            )
        else:
            click.secho("ℹ️ Nenhuma seção padrão configurada no momento.", fg="yellow")
            click.echo("Use 'onebridge set-section <nome_ou_id>' para configurar.")
        return

    try:
        sec = api.set_default_section(section=section, notebook=notebook)
        logger.info(f"Seção padrão definida: {sec.name} ({sec.id})")
        click.secho("⭐ Seção padrão configurada com sucesso!", fg="green", bold=True)
        click.echo(f"📑 Nome: {sec.name}")
        click.echo(f"🆔 ID:   {sec.id}")
    except RuntimeError as e:
        logger.error(f"Erro em set-section: {e}", exc_info=True)
        click.secho(f"❌ {e}", fg="red", err=True)
        sys.exit(1)
    except GraphAPIError as e:
        logger.error(f"Erro ao consultar Microsoft Graph em set-section: {e}", exc_info=True)
        click.secho(f"❌ Erro ao consultar Microsoft Graph: {e}", fg="red", err=True)
        sys.exit(1)
    except Exception as e:
        logger.error(f"Erro em set-section: {e}", exc_info=True)
        click.secho(f"❌ Erro: {e}", fg="red", err=True)
        sys.exit(1)
        click.echo(f"🆔 ID:   {sec.id}")
    except RuntimeError as e:
        click.secho(f"❌ {e}", fg="red", err=True)
        sys.exit(1)
    except GraphAPIError as e:
        click.secho(f"❌ Erro ao consultar Microsoft Graph: {e}", fg="red", err=True)
        sys.exit(1)
    except Exception as e:
        click.secho(f"❌ Erro: {e}", fg="red", err=True)
        sys.exit(1)


@cli.command("list-pages")
@click.argument("section_arg", required=False, default=None)
@click.option(
    "--section",
    "-s",
    "section_opt",
    default=None,
    help="Nome ou ID da seção (caso não fornecida como argumento).",
)
@click.option(
    "--notebook",
    "-n",
    default=None,
    help="Nome ou ID do caderno onde a seção está localizada (opcional).",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "json", "csv", "plain"], case_sensitive=False),
    default="table",
    help="Formato de saída: 'table' (padrão), 'json', 'csv' ou 'plain'.",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Atalho para exibir a saída em formato JSON.",
)
@click.option(
    "--sort-by",
    type=click.Choice(["order", "title", "modified", "created"], case_sensitive=False),
    default="order",
    help="Critério de ordenação das páginas (padrão: 'order').",
)
@click.option(
    "--asc",
    "order_direction",
    flag_value="asc",
    help="Força ordenação ascendente (A-Z ou mais antiga primeiro).",
)
@click.option(
    "--desc",
    "order_direction",
    flag_value="desc",
    help="Força ordenação descendente (Z-A ou mais recente primeiro).",
)
@click.option(
    "--client-id",
    default=None,
    help="Microsoft Entra (Azure) Application Client ID customizado.",
)
@click.option(
    "--authority",
    default=None,
    help="Authority URL.",
)
@click.option(
    "--db-path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=DB_PATH,
    help="Caminho do arquivo SQLite de autenticação/configurações.",
)
def list_pages_cmd(
    section_arg: Optional[str],
    section_opt: Optional[str],
    notebook: Optional[str],
    fmt: str,
    as_json: bool,
    sort_by: str,
    order_direction: Optional[str],
    client_id: Optional[str],
    authority: Optional[str],
    db_path: Path,
):
    """Lista as páginas de uma seção do OneNote (por ID ou Nome)."""
    section = section_opt or section_arg
    _list_pages_action(
        section=section,
        notebook=notebook,
        fmt=fmt,
        as_json=as_json,
        sort_by=sort_by,
        order_direction=order_direction,
        client_id=client_id,
        authority=authority,
        db_path=db_path,
    )


@cli.command("list_pages", hidden=True)
@click.argument("section_arg", required=False, default=None)
@click.option("--section", "-s", "section_opt", default=None)
@click.option("--notebook", "-n", default=None)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "json", "csv", "plain"], case_sensitive=False),
    default="table",
)
@click.option("--json", "as_json", is_flag=True)
@click.option(
    "--sort-by",
    type=click.Choice(["order", "title", "modified", "created"], case_sensitive=False),
    default="order",
)
@click.option("--asc", "order_direction", flag_value="asc")
@click.option("--desc", "order_direction", flag_value="desc")
@click.option("--client-id", default=None)
@click.option("--authority", default=None)
@click.option("--db-path", type=click.Path(dir_okay=False, path_type=Path), default=DB_PATH)
def list_pages_alias_cmd(
    section_arg: Optional[str],
    section_opt: Optional[str],
    notebook: Optional[str],
    fmt: str,
    as_json: bool,
    sort_by: str,
    order_direction: Optional[str],
    client_id: Optional[str],
    authority: Optional[str],
    db_path: Path,
):
    """Alias para 'list-pages'."""
    section = section_opt or section_arg
    _list_pages_action(
        section=section,
        notebook=notebook,
        fmt=fmt,
        as_json=as_json,
        sort_by=sort_by,
        order_direction=order_direction,
        client_id=client_id,
        authority=authority,
        db_path=db_path,
    )


@cli.command("pages")
@click.argument("section_arg", required=False, default=None)
@click.option("--section", "-s", "section_opt", default=None, help="Nome ou ID da seção.")
@click.option("--notebook", "-n", default=None, help="Nome ou ID do caderno.")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "json", "csv", "plain"], case_sensitive=False),
    default="table",
    help="Formato de saída.",
)
@click.option("--json", "as_json", is_flag=True, help="Atalho para saída em JSON.")
@click.option(
    "--sort-by",
    type=click.Choice(["order", "title", "modified", "created"], case_sensitive=False),
    default="order",
    help="Critério de ordenação.",
)
@click.option("--asc", "order_direction", flag_value="asc", help="Ordenação crescente.")
@click.option("--desc", "order_direction", flag_value="desc", help="Ordenação decrescente.")
@click.option("--client-id", default=None, help="Application Client ID.")
@click.option("--authority", default=None, help="Authority URL.")
@click.option(
    "--db-path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=DB_PATH,
    help="Caminho do banco SQLite.",
)
def pages_cmd(
    section_arg: Optional[str],
    section_opt: Optional[str],
    notebook: Optional[str],
    fmt: str,
    as_json: bool,
    sort_by: str,
    order_direction: Optional[str],
    client_id: Optional[str],
    authority: Optional[str],
    db_path: Path,
):
    """Lista e consulta páginas de uma seção do OneNote."""
    section = section_opt or section_arg
    _list_pages_action(
        section=section,
        notebook=notebook,
        fmt=fmt,
        as_json=as_json,
        sort_by=sort_by,
        order_direction=order_direction,
        client_id=client_id,
        authority=authority,
        db_path=db_path,
    )


def _format_size(size_bytes: int) -> str:
    """Format file size in human-readable units."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def _fetch_page_action(
    page: str,
    section: Optional[str],
    notebook: Optional[str],
    output_dir: Path,
    overwrite: bool,
    delay_ms: int,
    as_json: bool,
    client_id: Optional[str],
    authority: Optional[str],
    db_path: Path,
) -> None:
    """Core logic for fetch-page command."""
    logger.info(f"Executando fetch-page (page: {page}, section: {section}, notebook: {notebook}, output_dir: {output_dir})")
    api = OneBridgeAPI(client_id=client_id, authority=authority, db_path=db_path)

    try:
        result = api.fetch_page(
            page=page,
            section=section,
            notebook=notebook,
            output_dir=output_dir,
            overwrite=overwrite,
            delay_ms=delay_ms,
        )
        logger.info(f"fetch-page concluído: '{result.title}' -> {result.relative_path}")
    except ValueError as e:
        logger.warning(f"fetch-page aviso: {e}")
        click.secho(f"ℹ️ {e}", fg="yellow")
        sys.exit(1)
    except RuntimeError as e:
        logger.error(f"Erro em fetch-page: {e}", exc_info=True)
        click.secho(f"❌ {e}", fg="red", err=True)
        sys.exit(1)
    except GraphAPIError as e:
        logger.error(f"Erro ao consultar Microsoft Graph em fetch-page: {e}", exc_info=True)
        click.secho(f"❌ Erro ao consultar Microsoft Graph: {e}", fg="red", err=True)
        sys.exit(1)
    except Exception as e:
        logger.error(f"Erro inesperado em fetch-page: {e}", exc_info=True)
        click.secho(f"❌ Erro: {e}", fg="red", err=True)
        sys.exit(1)

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        return

    click.echo("")
    click.secho("🎉 Página exportada com sucesso em formato Markdown!", fg="green", bold=True)
    click.echo("-" * 70)
    click.echo(f"📄 {click.style('Título:', bold=True):<18} {result.title}")
    click.echo(f"🆔 {click.style('ID:', bold=True):<18} {result.page_id}")
    click.echo(f"📓 {click.style('Caderno:', bold=True):<18} {result.notebook_name}")
    sec_display = f"{result.section_group} / {result.section_name}" if result.section_group else result.section_name
    click.echo(f"📑 {click.style('Seção:', bold=True):<18} {sec_display}")
    click.echo(f"💾 {click.style('Arquivo:', bold=True):<18} {click.style(result.relative_path, fg='cyan')} ({_format_size(result.file_size_bytes)})")
    if result.images_downloaded > 0:
        click.echo(f"🖼️ {click.style('Imagens:', bold=True):<18} {result.images_downloaded} salva(s) na subpasta IMAGENS/")
    if result.attachments_downloaded > 0:
        click.echo(f"📎 {click.style('Anexos:', bold=True):<18} {result.attachments_downloaded} salvo(s) na subpasta ANEXOS/")
    click.echo("-" * 70)
    click.echo("")


@cli.command("fetch-page")
@click.argument("page_arg", required=False, default=None)
@click.option("--page", "-p", "page_opt", default=None, help="Título ou ID da página a ser exportada.")
@click.option("--section", "-s", default=None, help="Nome ou ID da seção para delimitar a busca (opcional).")
@click.option("--notebook", "-n", default=None, help="Nome ou ID do caderno para delimitar a busca (opcional).")
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(file_okay=False, writable=True, path_type=Path),
    default=DEFAULT_EXPORT_DIR,
    help="Diretório raiz de saída para as notas (padrão: ARQUIVOS/).",
)
@click.option(
    "--overwrite/--no-overwrite",
    default=True,
    help="Sobrescrever arquivo se já existir (padrão: True).",
)
@click.option(
    "--delay-ms",
    type=int,
    default=DEFAULT_REQUEST_DELAY_MS,
    help=f"Pausa entre requisições HTTP em milissegundos (padrão: {DEFAULT_REQUEST_DELAY_MS}ms).",
)
@click.option("--json", "as_json", is_flag=True, help="Exibe o resultado em formato JSON.")
@click.option("--client-id", default=None, help="Application Client ID.")
@click.option("--authority", default=None, help="Authority URL.")
@click.option(
    "--db-path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=DB_PATH,
    help="Caminho do arquivo SQLite de autenticação/configurações.",
)
def fetch_page_cmd(
    page_arg: Optional[str],
    page_opt: Optional[str],
    section: Optional[str],
    notebook: Optional[str],
    output_dir: Path,
    overwrite: bool,
    delay_ms: int,
    as_json: bool,
    client_id: Optional[str],
    authority: Optional[str],
    db_path: Path,
):
    """Recupera uma página pelo Título ou ID e salva em Markdown com imagens e anexos."""
    page = page_opt or page_arg
    if not page:
        click.secho(
            "❌ Informe o título ou ID da página: 'onebridge fetch-page <titulo_ou_id>'",
            fg="red",
            err=True,
        )
        sys.exit(1)

    _fetch_page_action(
        page=page,
        section=section,
        notebook=notebook,
        output_dir=output_dir,
        overwrite=overwrite,
        delay_ms=delay_ms,
        as_json=as_json,
        client_id=client_id,
        authority=authority,
        db_path=db_path,
    )


@cli.command("fetch_page", hidden=True)
@click.argument("page_arg", required=False, default=None)
@click.option("--page", "-p", "page_opt", default=None)
@click.option("--section", "-s", default=None)
@click.option("--notebook", "-n", default=None)
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(file_okay=False, writable=True, path_type=Path),
    default=DEFAULT_EXPORT_DIR,
)
@click.option("--overwrite/--no-overwrite", default=True)
@click.option(
    "--delay-ms",
    type=int,
    default=DEFAULT_REQUEST_DELAY_MS,
)
@click.option("--json", "as_json", is_flag=True)
@click.option("--client-id", default=None)
@click.option("--authority", default=None)
@click.option("--db-path", type=click.Path(dir_okay=False, path_type=Path), default=DB_PATH)
def fetch_page_alias_cmd(
    page_arg: Optional[str],
    page_opt: Optional[str],
    section: Optional[str],
    notebook: Optional[str],
    output_dir: Path,
    overwrite: bool,
    delay_ms: int,
    as_json: bool,
    client_id: Optional[str],
    authority: Optional[str],
    db_path: Path,
):
    """Alias para 'fetch-page'."""
    page = page_opt or page_arg
    if not page:
        click.secho(
            "❌ Informe o título ou ID da página: 'onebridge fetch-page <titulo_ou_id>'",
            fg="red",
            err=True,
        )
        sys.exit(1)

    _fetch_page_action(
        page=page,
        section=section,
        notebook=notebook,
        output_dir=output_dir,
        overwrite=overwrite,
        delay_ms=delay_ms,
        as_json=as_json,
        client_id=client_id,
        authority=authority,
        db_path=db_path,
    )


def _fetch_pages_action(
    notebook: Optional[str],
    section: Optional[str],
    recursive: bool,
    output_dir: Path,
    overwrite: bool,
    delay_ms: int,
    as_json: bool,
    client_id: Optional[str],
    authority: Optional[str],
    db_path: Path,
) -> None:
    """Core logic for fetch-pages command."""
    logger.info(f"Executando fetch-pages (caderno: {notebook}, seção: {section}, recursive: {recursive}, output_dir: {output_dir})")
    api = OneBridgeAPI(client_id=client_id, authority=authority, db_path=db_path)

    def on_progress(page_res: PageExportResultDTO, current: int, total: int):
        if not as_json:
            if page_res.success:
                assets_str = ""
                if page_res.images_downloaded > 0 or page_res.attachments_downloaded > 0:
                    parts = []
                    if page_res.images_downloaded > 0:
                        parts.append(f"🖼️ {page_res.images_downloaded}")
                    if page_res.attachments_downloaded > 0:
                        parts.append(f"📎 {page_res.attachments_downloaded}")
                    assets_str = f" ({', '.join(parts)})"
                click.echo(
                    f"[{current}/{total}] 📄 {click.style(page_res.title, bold=True)} ➔ {click.style(page_res.relative_path, fg='cyan')}{assets_str}"
                )
            else:
                click.secho(
                    f"[{current}/{total}] ❌ {page_res.title}: {page_res.error_message}",
                    fg="red",
                    err=True,
                )

    if not as_json:
        target_name = section or notebook or "padrão"
        click.echo("")
        click.secho(f"🚀 Iniciando exportação de notas ({target_name})...", fg="blue", bold=True)
        click.echo("")

    try:
        result = api.fetch_pages(
            notebook=notebook,
            section=section,
            recursive=recursive,
            output_dir=output_dir,
            overwrite=overwrite,
            delay_ms=delay_ms,
            on_progress=on_progress,
        )
        logger.info(f"fetch-pages concluído com sucesso: {result.successful_pages}/{result.total_pages} páginas em {result.elapsed_seconds}s")
    except ValueError as e:
        logger.warning(f"fetch-pages aviso: {e}")
        click.secho(f"ℹ️ {e}", fg="yellow")
        sys.exit(1)
    except RuntimeError as e:
        logger.error(f"Erro em fetch-pages: {e}", exc_info=True)
        click.secho(f"❌ {e}", fg="red", err=True)
        sys.exit(1)
    except GraphAPIError as e:
        logger.error(f"Erro ao consultar Microsoft Graph em fetch-pages: {e}", exc_info=True)
        click.secho(f"❌ Erro ao consultar Microsoft Graph: {e}", fg="red", err=True)
        sys.exit(1)
    except Exception as e:
        logger.error(f"Erro inesperado em fetch-pages: {e}", exc_info=True)
        click.secho(f"❌ Erro: {e}", fg="red", err=True)
        sys.exit(1)

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        return

    click.echo("")
    click.echo("=" * 70)
    click.secho("🎉 Exportação em lote concluída com sucesso!", fg="green", bold=True)
    click.echo(f"📁 {click.style('Diretório de saída:', bold=True):<24} {result.output_directory}")
    click.echo(
        f"📄 {click.style('Páginas exportadas:', bold=True):<24} {result.successful_pages} de {result.total_pages} ({result.failed_pages} falha(s))"
    )
    click.echo(f"🖼️ {click.style('Total de imagens:', bold=True):<24} {result.total_images}")
    click.echo(f"📎 {click.style('Total de anexos:', bold=True):<24} {result.total_attachments}")
    click.echo(f"⏱️ {click.style('Tempo decorrido:', bold=True):<24} {result.elapsed_seconds}s")
    click.echo("=" * 70)
    click.echo("")


@cli.command("fetch-pages")
@click.option("--notebook", "-n", default=None, help="Nome ou ID do caderno a exportar.")
@click.option("--section", "-s", default=None, help="Nome ou ID da seção a exportar.")
@click.option(
    "--direct-only",
    "--no-recursive",
    "direct_only",
    is_flag=True,
    help="Exporta apenas seções do nível raiz do caderno (ignora subseções).",
)
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(file_okay=False, writable=True, path_type=Path),
    default=DEFAULT_EXPORT_DIR,
    help="Diretório raiz de saída para as notas (padrão: ARQUIVOS/).",
)
@click.option(
    "--overwrite/--no-overwrite",
    default=True,
    help="Sobrescrever arquivos se já existirem (padrão: True).",
)
@click.option(
    "--delay-ms",
    type=int,
    default=DEFAULT_REQUEST_DELAY_MS,
    help=f"Pausa entre requisições HTTP em milissegundos (padrão: {DEFAULT_REQUEST_DELAY_MS}ms).",
)
@click.option("--json", "as_json", is_flag=True, help="Exibe o resultado consolidado em formato JSON.")
@click.option("--client-id", default=None, help="Application Client ID.")
@click.option("--authority", default=None, help="Authority URL.")
@click.option(
    "--db-path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=DB_PATH,
    help="Caminho do arquivo SQLite de autenticação/configurações.",
)
def fetch_pages_cmd(
    notebook: Optional[str],
    section: Optional[str],
    direct_only: bool,
    output_dir: Path,
    overwrite: bool,
    delay_ms: int,
    as_json: bool,
    client_id: Optional[str],
    authority: Optional[str],
    db_path: Path,
):
    """Recupera múltiplas páginas (de um caderno ou seção) e salva em Markdown."""
    recursive = not direct_only
    _fetch_pages_action(
        notebook=notebook,
        section=section,
        recursive=recursive,
        output_dir=output_dir,
        overwrite=overwrite,
        delay_ms=delay_ms,
        as_json=as_json,
        client_id=client_id,
        authority=authority,
        db_path=db_path,
    )


@cli.command("fetch_pages", hidden=True)
@click.option("--notebook", "-n", default=None)
@click.option("--section", "-s", default=None)
@click.option("--direct-only", "--no-recursive", "direct_only", is_flag=True)
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(file_okay=False, writable=True, path_type=Path),
    default=DEFAULT_EXPORT_DIR,
)
@click.option("--overwrite/--no-overwrite", default=True)
@click.option(
    "--delay-ms",
    type=int,
    default=DEFAULT_REQUEST_DELAY_MS,
)
@click.option("--json", "as_json", is_flag=True)
@click.option("--client-id", default=None)
@click.option("--authority", default=None)
@click.option("--db-path", type=click.Path(dir_okay=False, path_type=Path), default=DB_PATH)
def fetch_pages_alias_cmd(
    notebook: Optional[str],
    section: Optional[str],
    direct_only: bool,
    output_dir: Path,
    overwrite: bool,
    delay_ms: int,
    as_json: bool,
    client_id: Optional[str],
    authority: Optional[str],
    db_path: Path,
):
    """Alias para 'fetch-pages'."""
    recursive = not direct_only
    _fetch_pages_action(
        notebook=notebook,
        section=section,
        recursive=recursive,
        output_dir=output_dir,
        overwrite=overwrite,
        delay_ms=delay_ms,
        as_json=as_json,
        client_id=client_id,
        authority=authority,
        db_path=db_path,
    )


@cli.command("tui")
@click.option("--client-id", default=None, help="Microsoft Entra (Azure) Application Client ID.")
@click.option("--authority", default=None, help="Authority URL.")
@click.option(
    "--db-path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=DB_PATH,
    help="Caminho do arquivo SQLite para tokens e configurações.",
)
def tui_cmd(client_id: Optional[str], authority: Optional[str], db_path: Path):
    """Inicia a interface interativa de terminal (TUI) do OneBridge."""
    from onebridge.tui.app import run_tui

    logger.info("Iniciando modo TUI interativo.")
    api = OneBridgeAPI(client_id=client_id, authority=authority, db_path=db_path)
    run_tui(api=api)


if __name__ == "__main__":
    cli()


