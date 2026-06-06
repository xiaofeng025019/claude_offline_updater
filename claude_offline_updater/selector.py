"""Interactive machine selection (questionary)"""

import questionary
from prompt_toolkit.keys import Keys
from rich.table import Table

from .display import console
from .i18n import t

# Special marker: user selected 'Back'
_BACK_VALUE = "__back__"


def select_machines(scan_results: list[dict], target_version: str) -> list[dict]:
    """Interactive multi-select machines; returns [] if user backs out.

    Two-step flow:
      1. Checkbox to select machines (no back option here — it's
         non-obvious that checking "← 返回" inside a checkbox actually
         goes back, since users naturally focus on machines)
      2. Confirm prompt: "Update N machines? [Y/n]"

    Either step's "no" / ESC returns [], which the caller treats as
    "user cancelled".
    """
    if not scan_results:
        return []

    # Build choices (machines only, no "← 返回" — handled in step 2)
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

    # Step 1: machine selection
    q1 = questionary.checkbox(t("select_prompt"), choices=choices)
    _bind_esc(q1)
    selected = q1.ask()

    # ESC pressed → back out
    if selected is None:
        return []

    # Nothing selected → back out
    if not selected:
        return []

    # Step 2: confirm before deploying. The "← 返回" escape hatch is
    # here as a confirm step (Y/n) so the user has an explicit final
    # chance to abort — pressing Enter on a confirm by default = yes.
    q2 = questionary.confirm(
        t("confirm_update", count=len(selected)),
        default=True,
    )
    _bind_esc(q2)
    confirmed = q2.ask()

    # ESC at confirm or answered no → back out
    if confirmed is None or not confirmed:
        return []

    return selected


def _bind_esc(question):
    """Add ESC key binding to a questionary Question, making ESC behave like Ctrl+C."""
    from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
    extra = KeyBindings()

    @extra.add(Keys.Escape, eager=True)
    def _on_esc(event):
        event.app.exit(exception=KeyboardInterrupt, style="class:aborting")

    question.application.key_bindings = merge_key_bindings(
        [question.application.key_bindings, extra]
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
