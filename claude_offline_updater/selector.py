"""Interactive machine selection (questionary)"""

import questionary
from prompt_toolkit.keys import Keys
from rich.table import Table

from .display import console
from .i18n import t

# Special marker: user selected 'Back'
_BACK_VALUE = "__back__"


def select_machines(scan_results: list[dict], target_version: str) -> list[dict]:
    """Interactive multi-select machines; selecting 'Back' returns empty list"""
    if not scan_results:
        return []

    # Build choices
    choices = []
    for r in scan_results:
        ver = r["version"]
        if ver == target_version:
            label = f"{r['name']:20s} {r['host']:18s} {ver} [{t('status_latest')}]"
        elif ver in (t("status_not_installed"), t("status_conn_failed")):
            label = f"{r['name']:20s} {r['host']:18s} {ver} → {target_version}"
        else:
            label = f"{r['name']:20s} {r['host']:18s} {ver} → {target_version}"

        # Already latest defaults to unchecked, others default to checked
        checked = ver != target_version
        choices.append(questionary.Choice(title=label, value=r, checked=checked))

    # Add separator and back option
    choices.append(questionary.Separator())
    choices.append(questionary.Choice(
        title=t("config_return"),
        value=_BACK_VALUE,
        checked=False,
    ))

    # Display version info table
    _show_preview_table(scan_results, target_version)

    # Multi-select (with ESC bound)
    q = questionary.checkbox(
        t("select_prompt"),
        choices=choices,
    )
    kb = q.application.key_bindings

    @kb.add(Keys.Escape, eager=True)
    def _on_esc(event):
        event.app.exit(exception=KeyboardInterrupt, style="class:aborting")

    selected = q.ask()

    # ESC or no selection → go back
    if selected is None:
        return []

    # If user selected '← 返回' at all → go back regardless of other selections
    if _BACK_VALUE in selected:
        return []

    return selected


def _show_preview_table(results: list[dict], target_version: str):
    """Display preview table"""
    table = Table(title=t("preview_title"), show_lines=False)
    table.add_column(t("col_name"), style="cyan")
    table.add_column(t("col_host"), style="white")
    table.add_column(t("col_port"), style="white")
    table.add_column(t("col_version"), style="white")
    table.add_column(t("col_status"), style="white")

    for r in results:
        ver = r["version"]
        if ver == target_version:
            status = f"[green]{t('status_latest')}[/green]"
            ver_style = f"[green]{ver}[/green]"
        elif ver in (t("status_not_installed"), t("status_conn_failed")):
            status = f"[red]{ver}[/red]"
            ver_style = f"[red]{ver}[/red]"
        else:
            status = f"[yellow]→ {target_version}[/yellow]"
            ver_style = f"[yellow]{ver}[/yellow]"

        table.add_row(r["name"], r["host"], str(r["port"]), ver_style, status)

    console.print()
    console.print(table)
    console.print()
