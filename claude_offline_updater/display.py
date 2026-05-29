"""Rich unified display module"""

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table

from .i18n import t

console = Console()


def _prefix(label: str) -> str:
    """Return a Rich-safe bracket prefix like \\[name] — Rich eats [x] as style tags"""
    if not label:
        return ""
    return f"\\[{label}] "


def info(msg: str):
    console.print(f"[blue][INFO][/blue] {msg}")


def success(msg: str):
    console.print(f"[green][OK][/green] {msg}")


def warn(msg: str):
    console.print(f"[yellow][WARN][/yellow] {msg}")


def error(msg: str):
    console.print(f"[red][ERROR][/red] {msg}")


def header(title: str):
    console.print(Panel(title, style="bold", expand=False))


def create_download_progress() -> Progress:
    """Create download progress bar"""
    return Progress(
        "[progress.description]{task.description}",
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
    )


def show_scan_results(results: list[dict], target_version: str):
    """Display scan results table"""
    table = Table(title=t("scan_result_title"))
    table.add_column(t("col_name"), style="cyan")
    table.add_column(t("col_host"), style="white")
    table.add_column(t("col_port"), style="white")
    table.add_column(t("col_version"), style="white")
    table.add_column(t("col_status"), style="white")

    for r in results:
        ver = r["version"]
        if ver == target_version:
            status = f"[green]{t('status_latest')}[/green]"
            ver_display = f"[green]{ver}[/green]"
        elif ver == t("status_not_installed"):
            status = f"[yellow]{t('status_not_installed')}[/yellow]"
            ver_display = f"[yellow]{t('status_not_installed')}[/yellow]"
        elif ver == t("status_conn_failed"):
            status = f"[red]{t('status_conn_failed')}[/red]"
            ver_display = f"[red]{t('status_conn_failed')}[/red]"
        else:
            status = f"[yellow]{t('status_need_update')} → {target_version}[/yellow]"
            ver_display = f"[yellow]{ver}[/yellow]"

        table.add_row(r["name"], r["host"], str(r["port"]), ver_display, status)

    console.print(table)


def show_update_results(results: list[dict]):
    """Display update results table"""
    table = Table(title=t("result_title"))
    table.add_column(t("col_machine"), style="cyan")
    table.add_column(t("col_host"), style="white")
    table.add_column(t("col_result"), style="white")
    table.add_column(t("col_detail"), style="white")

    ok_count = fail_count = skip_count = 0

    for r in results:
        status = r["status"]
        if status == "success":
            table.add_row(r["name"], r["host"], f"[green]{t('result_success')}[/green]",
                          f"→ {r['to_version']}")
            ok_count += 1
        elif status == "failed":
            table.add_row(r["name"], r["host"], f"[red]{t('result_failed')}[/red]",
                          r.get("detail", ""))
            fail_count += 1
        elif status == "skipped":
            table.add_row(r["name"], r["host"], f"[dim]{t('result_skipped')}[/dim]",
                          f"{r.get('from_version', '')} {t('result_already_latest')}")
            skip_count += 1

    console.print(table)
    console.print(
        f"\n  [bold]{t('total')}:[/bold] "
        f"{t('success_count')} [green]{ok_count}[/green]  "
        f"{t('failed_count')} [red]{fail_count}[/red]  "
        f"{t('skipped_count')} [dim]{skip_count}[/dim]\n"
    )


def show_history_table(records: list[dict]):
    """Display update history table (backward-compatible alias)"""
    show_oplog_table(records)


def show_oplog_table(records: list[dict]):
    """Display operation log table"""
    table = Table(title=t("oplog_title"))
    table.add_column(t("col_time"), style="dim")
    table.add_column(t("col_machine"), style="cyan")
    table.add_column(t("col_host"), style="white")
    table.add_column(t("col_event"), style="white")
    table.add_column(t("col_detail"), style="white")
    table.add_column(t("col_duration"), style="white")

    for r in records:
        etype = r.get("event_type", "update")

        if etype == "update":
            status = r.get("status", "")
            if status == "success":
                event_str = f"[green]✓[/green] {t('event_update')}"
            elif status == "failed":
                event_str = f"[red]✗[/red] {t('event_update')}"
            else:
                event_str = f"[dim]─[/dim] {t('event_update')}"
            from_ver = r.get("from_version", "-")
            to_ver = r.get("to_version", "")
            detail_str = f"{from_ver} → {to_ver}" if from_ver and from_ver != "-" else f"→ {to_ver}"
            duration = r.get("duration_seconds")
            duration_str = f"{duration:.1f}s" if duration else "-"

        elif etype == "install":
            status = r.get("status", "")
            if status == "success":
                event_str = f"[green]✓[/green] {t('event_install')}"
            elif status == "failed":
                event_str = f"[red]✗[/red] {t('event_install')}"
            else:
                event_str = f"[dim]─[/dim] {t('event_install')}"
            to_ver = r.get("to_version", "")
            detail_str = f"→ {to_ver}" if to_ver else ""
            duration = r.get("duration_seconds")
            duration_str = f"{duration:.1f}s" if duration else "-"

        elif etype == "add":
            event_str = f"[cyan]{t('event_add')}[/cyan]"
            detail_str = ""
            duration_str = "-"

        elif etype == "remove":
            event_str = f"[red]{t('event_remove')}[/red]"
            detail_str = ""
            duration_str = "-"

        elif etype == "rename":
            event_str = f"[yellow]{t('event_rename')}[/yellow]"
            detail_str = t("detail_renamed", old=r.get("old_name", "?"), new=r["machine_name"])
            duration_str = "-"

        elif etype == "ip_change":
            event_str = f"[yellow]{t('event_ip_change')}[/yellow]"
            detail_str = t("detail_ip_changed", old=r.get("old_host", "?"), new=r["machine_host"])
            duration_str = "-"

        elif etype == "first_seen":
            event_str = f"[blue]{t('event_first_seen')}[/blue]"
            mid = r.get("machine_id", "")
            detail_str = t("detail_first_seen", mid=f"{mid[:8]}..." if mid else "-")
            duration_str = "-"

        else:
            event_str = etype
            detail_str = "-"
            duration_str = "-"

        table.add_row(
            r["timestamp"][:19] if r.get("timestamp") else "-",
            r["machine_name"],
            r["machine_host"],
            event_str,
            detail_str,
            duration_str,
        )

    console.print(table)


def show_config_panels(config):
    """Display config with structured panels"""
    from .config import DEFAULTS

    s = config.settings
    loc = config.local

    # ── Global settings panel ──
    settings_rows = [
        ("max_versions", str(s.max_versions), str(DEFAULTS.get("max_versions", ""))),
        ("platform", s.platform, str(DEFAULTS.get("platform", ""))),
        ("lang", s.lang, str(DEFAULTS.get("lang", ""))),
        ("connect_timeout", f"{s.connect_timeout}s", f"{DEFAULTS.get('connect_timeout', '')}s"),
        ("download_timeout", f"{s.download_timeout}s", f"{DEFAULTS.get('download_timeout', '')}s"),
        ("max_retries", str(s.max_retries), str(DEFAULTS.get("max_retries", ""))),
        ("max_workers", str(s.max_workers), str(DEFAULTS.get("max_workers", ""))),
        ("scp_bandwidth_limit",
         f"{s.scp_bandwidth_limit} KB/s" if s.scp_bandwidth_limit
         else "0 (unlimited)",
         "0 (unlimited)"),
        ("ssh_host_key_policy", s.ssh_host_key_policy,
         DEFAULTS.get("ssh_host_key_policy", "")),
        ("download_base", s.download_base, ""),
        ("local_cache_dir", s.local_cache_dir, ""),
        ("remote_claude_bin", s.remote_claude_bin, ""),
        ("remote_versions_dir", s.remote_versions_dir, ""),
        ("remote_tmp_dir", s.remote_tmp_dir, ""),
    ]

    st = Table(show_header=True, header_style="bold", expand=False, show_lines=False)
    st.add_column(t("config_col_key"), style="cyan", no_wrap=True)
    st.add_column(t("config_col_value"), style="white")
    st.add_column(t("config_col_default"), style="dim", no_wrap=True)
    for key, val, default in settings_rows:
        changed = default and val != default
        val_display = f"[yellow]{val}[/yellow]" if changed else val
        default_display = f"{default} [yellow]*[/yellow]" if changed else default
        st.add_row(key, val_display, default_display)

    # ── Local settings panel ──
    lt = Table(show_header=True, header_style="bold", expand=False)
    lt.add_column(t("config_col_key"), style="cyan", min_width=20)
    lt.add_column(t("config_col_value"), style="white", min_width=30)
    if loc.enabled:
        enabled_str = f"[green]{t('config_enabled')}[/green]"
    else:
        enabled_str = f"[red]{t('config_disabled')}[/red]"
    lt.add_row("enabled", enabled_str)
    lt.add_row("claude_bin", loc.claude_bin)
    lt.add_row("versions_dir", loc.versions_dir)

    # ── Machine list panel ──
    mt = Table(show_header=True, header_style="bold", expand=False)
    mt.add_column(t("config_col_m_name"), style="cyan", min_width=12)
    mt.add_column(t("config_col_m_host"), style="white", min_width=18)
    mt.add_column(t("config_col_m_port"), style="white", min_width=6)
    mt.add_column(t("config_col_m_user"), style="white", min_width=8)
    mt.add_column(t("config_col_m_id"), style="dim", min_width=12)
    for m in config.machines:
        mid_display = f"{m.machine_id[:8]}..." if m.machine_id else "-"
        mt.add_row(m.name, m.host, str(m.port), m.user, mid_display)

    console.print()
    console.print(Panel(st, title=t("config_panel_settings"), expand=False))
    console.print(Panel(lt, title=t("config_panel_local"), expand=False))
    if config.machines:
        console.print(Panel(mt, title=t("config_panel_machines"), expand=False))
    else:
        console.print(Panel(f"[dim]{t('no_machines')}[/dim]",
                            title=t("config_panel_machines"), expand=False))
    console.print()
