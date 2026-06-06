"""Interactive machine selection (questionary)"""

import questionary
from prompt_toolkit.keys import Keys
from rich.table import Table

from .display import console
from .i18n import t


def select_machines(scan_results: list[dict], target_version: str) -> list[dict] | None:
    """Interactive single-step machine selection.

    Returns:
      - None      → user pressed ESC. Callers should return to the
                    previous screen with no warning.
      - [dict...] → run the update on these selected machines.

    Back-out happens only via ESC; the prompt's instruction line
    tells the user how. There is no '← Back' option in the list.
    """
    if not scan_results:
        return []

    # Build the checkbox choices — machines only, no back option.
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

    # Display version info table
    _show_preview_table(scan_results, target_version)

    q = questionary.checkbox(
        t("select_prompt"),
        choices=choices,
        instruction=t("instruction_back"),
    )
    _bind_esc(q)
    selected = q.ask()

    # ESC pressed → silent back-out
    if selected is None:
        return None

    return selected


def _bind_esc(question):
    """Add ESC key binding to a questionary Question, making ESC behave like Ctrl+C."""
    from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
    extra = KeyBindings()

    @extra.add(Keys.Escape, eager=True)
    def _on_esc(event):
        event.app.exit(exception=KeyboardInterrupt, style="class:aborting")

    # Put `extra` first so our eager binding runs before any default
    # Escape handler from questionary (e.g. in confirm/prompt).
    question.application.key_bindings = merge_key_bindings(
        [extra, question.application.key_bindings]
    )
    return question


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
