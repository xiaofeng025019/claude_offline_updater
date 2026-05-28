"""Click CLI definitions"""

import sys

import click

from . import __version__, get_version_display
from .config import DEFAULTS, Config, Machine, _shorten_path
from .display import console, error, header, info, show_scan_results, success, warn
from .downloader import DownloadError
from .i18n import get_lang, set_lang, t


@click.group(invoke_without_command=True)
@click.option("--config", "-c", "config_path", default=None,
              help="Config file path (default: ~/.config/claude-update/config.yaml)")
@click.option("--lang", "-l", default=None, type=click.Choice(["zh", "en"]),
              help="Language (zh/en)")
@click.version_option(version=__version__)
@click.pass_context
def cli(ctx, config_path, lang):
    """Claude Code Offline Updater - Multi-machine batch update management"""
    ctx.ensure_object(dict)

    auto_created = False
    default_path = Config.default_config_path()
    if config_path is None and not default_path.exists():
        auto_created = True

    try:
        ctx.obj["config"] = Config.load(config_path)
    except FileNotFoundError as e:
        error(str(e))
        sys.exit(1)

    if lang:
        set_lang(lang)
    elif ctx.obj["config"].settings.lang:
        set_lang(ctx.obj["config"].settings.lang)

    if auto_created:
        info(t("config_welcome"))
        success(f"{t('config_auto_created')}: {default_path}")

    if ctx.invoked_subcommand is None:
        _interactive_main(ctx)


def _interactive_main(ctx):
    """Interactive main menu"""
    import questionary

    header(f"{t('app_title')}  {get_version_display()}")

    while True:
        action = questionary.select(
            t("menu_prompt"),
            choices=[
                questionary.Choice(t("menu_scan"), value="scan"),
                questionary.Choice(t("menu_update"), value="update"),
                questionary.Choice(t("menu_history"), value="history"),
                questionary.Choice(t("menu_config"), value="config"),
                questionary.Choice(t("menu_cache"), value="cache"),
                questionary.Separator(),
                questionary.Choice(t("menu_quit"), value="quit"),
            ],
        ).ask()

        if action is None or action == "quit":
            info(t("goodbye"))
            break

        try:
            if action == "scan":
                _interactive_scan(ctx)
            elif action == "update":
                _interactive_update(ctx.obj["config"])
            elif action == "history":
                _interactive_history(ctx)
            elif action == "config":
                _interactive_config(ctx)
            elif action == "cache":
                _interactive_cache(ctx)
        except KeyboardInterrupt:
            console.print()
            continue


def _interactive_scan(ctx):
    """Interactive scan"""
    from .downloader import get_latest_version
    from .scanner import scan_all

    config = ctx.obj["config"]
    header(t("scan_title"))
    try:
        target_version = get_latest_version(config.settings)
    except DownloadError as e:
        error(str(e))
        sys.exit(1)
    success(f"{t('latest_version')}: {target_version}")

    results = scan_all(config.machines, config.settings, local=config.local)
    show_scan_results(results, target_version)


def _interactive_history(ctx):
    """Interactive history"""
    import questionary

    from .display import show_history_table
    from .history import get_history

    config = ctx.obj["config"]
    machine_names = [m.name for m in config.machines]
    machine_hosts = {m.name: m.host for m in config.machines}
    filter_choice = questionary.select(
        t("history_filter"),
        choices=[t("all_machines")] + machine_names,
    ).ask()

    if filter_choice in (None, t("all_machines")):
        machine = None
        host = None
    else:
        machine = filter_choice
        host = machine_hosts.get(filter_choice)
    records = get_history(machine=machine, host=host, limit=50)

    if not records:
        info(t("no_history"))
    else:
        show_history_table(records)


def _interactive_config(ctx):
    """Interactive config management"""
    import questionary

    from .display import show_config_panels

    config = ctx.obj["config"]
    show_config_panels(config)

    action = questionary.select(
        t("config_action"),
        choices=[
            t("config_edit_settings"),
            t("config_edit_local"),
            t("config_edit_machine"),
            t("config_add"),
            t("config_remove"),
            t("config_set_lang"),
            questionary.Separator(),
            t("config_return"),
        ],
    ).ask()

    if action == t("config_edit_settings"):
        _edit_settings(config)

    elif action == t("config_edit_local"):
        _edit_local(config)

    elif action == t("config_edit_machine"):
        _edit_machine(config)

    elif action == t("config_set_lang"):
        current = get_lang()
        current_name = t("lang_zh") if current == "zh" else t("lang_en")
        info(f"{t('config_current_lang')}: {current_name} ({current})")

        lang_choice = questionary.select(
            t("config_select_lang"),
            choices=[
                questionary.Choice(f"{t('lang_zh')} (zh)", value="zh"),
                questionary.Choice(f"{t('lang_en')} (en)", value="en"),
            ],
        ).ask()

        if lang_choice and lang_choice != current:
            set_lang(lang_choice)
            config.settings.lang = lang_choice
            config.save()
            new_name = t("lang_zh") if lang_choice == "zh" else t("lang_en")
            success(f"{t('config_lang_changed')} {new_name} ({lang_choice})")

    elif action == t("config_add"):
        name = questionary.text(t("input_name")).ask()
        if not name:
            return
        host = questionary.text(t("input_host")).ask()
        if not host:
            return
        port = questionary.text(t("input_port"), default="22").ask()
        user = questionary.text(t("input_user"), default="root").ask()

        try:
            port_val = int(port or 22)
            if not (1 <= port_val <= 65535):
                raise ValueError
        except ValueError:
            error(t("invalid_port", port=port))
            return
        machine = Machine(name=name, host=host, port=port_val,
                          user=user or "root")
        try:
            config.add_machine(machine)
            config.save()
            success(f"{t('machine_added')}: {name} ({host}:{port})")
        except ValueError as e:
            error(str(e))

    elif action == t("config_remove"):
        machine_names = [m.name for m in config.machines]
        if not machine_names:
            info(t("no_machines"))
            return
        name = questionary.select(t("select_remove"), choices=machine_names).ask()
        if name and config.remove_machine(name):
            config.save()
            success(f"{t('machine_removed')}: {name}")


def _edit_settings(config):
    """Interactive global settings editor"""
    import questionary


    s = config.settings
    fields = [
        ("max_versions", str(s.max_versions), str, "3"),
        ("connect_timeout", str(s.connect_timeout), int, "10"),
        ("download_timeout", str(s.download_timeout), int, "300"),
        ("max_retries", str(s.max_retries), int, "3"),
        ("max_workers", str(s.max_workers), int, "5"),
        ("scp_bandwidth_limit", str(s.scp_bandwidth_limit), int, "0"),
        ("platform", s.platform, str, "linux-x64"),
        ("download_base", s.download_base, str, DEFAULTS["download_base"]),
        ("local_cache_dir", _shorten_path(s.local_cache_dir), str, DEFAULTS["local_cache_dir"]),
        ("remote_claude_bin", _shorten_path(s.remote_claude_bin), str, "~/.local/bin/claude"),
        ("remote_versions_dir", _shorten_path(s.remote_versions_dir),
         str, "~/.local/share/claude/versions"),
        ("remote_tmp_dir", s.remote_tmp_dir, str, "/tmp/claude-update"),
        ("ssh_host_key_policy", s.ssh_host_key_policy, str, "warn"),
    ]

    choices = [
        questionary.Choice(f"{k} = {v}  (default: {d})", value=k)
        for k, v, _, d in fields
    ]
    choices.append(questionary.Choice(t("config_return"), value="__back__"))

    field_map = {k: (v, tp) for k, v, tp, _ in fields}

    while True:
        field = questionary.select(t("config_edit_settings"), choices=choices).ask()
        if not field or field == "__back__":
            break

        old_val, tp = field_map[field]
        new_val = questionary.text(
            f"{field} [{t('config_edit_prompt')}]",
            default=old_val,
        ).ask()

        if new_val is None or new_val == old_val:
            info(t("config_no_change"))
            continue

        try:
            if tp is int:
                setattr(s, field, int(new_val))
            else:
                setattr(s, field, new_val)
            field_map[field] = (new_val, tp)
            for i, (k, _, _, d) in enumerate(fields):
                if k == field:
                    choices[i] = questionary.Choice(
                        f"{k} = {new_val}  (default: {d})", value=k
                    )
                    break
            config.save()
            success(f"{field}: {old_val} → {new_val}")
        except (ValueError, TypeError) as e:
            error(str(e))


def _edit_local(config):
    """Interactive local settings editor"""
    import questionary

    loc = config.local
    fields = [
        ("enabled", str(loc.enabled), lambda v: v.lower() in ("true", "1", "yes")),
        ("claude_bin", _shorten_path(loc.claude_bin), str),
        ("versions_dir", _shorten_path(loc.versions_dir), str),
    ]

    choices = [
        questionary.Choice(f"{k} = {v}", value=k)
        for k, v, _ in fields
    ]
    choices.append(questionary.Choice(t("config_return"), value="__back__"))

    field_map = {k: (v, tp) for k, v, tp in fields}

    while True:
        field = questionary.select(t("config_edit_local"), choices=choices).ask()
        if not field or field == "__back__":
            break

        old_val, tp = field_map[field]
        new_val = questionary.text(
            f"{field} [{t('config_edit_prompt')}]",
            default=old_val,
        ).ask()

        if new_val is None or new_val == old_val:
            info(t("config_no_change"))
            continue

        try:
            converted = tp(new_val)
            setattr(loc, field, converted)
            field_map[field] = (new_val, tp)
            for i, (k, _, _) in enumerate(fields):
                if k == field:
                    choices[i] = questionary.Choice(
                        f"{k} = {new_val}", value=k
                    )
                    break
            config.save()
            success(f"{field}: {old_val} → {new_val}")
        except (ValueError, TypeError) as e:
            error(str(e))


def _edit_machine(config):
    """Interactive machine config editor"""
    import questionary

    if not config.machines:
        info(t("no_machines"))
        return

    machine_names = [m.name for m in config.machines]
    name = questionary.select(t("select_edit_machine"), choices=machine_names).ask()
    if not name:
        return

    machine = config.find_machine(name)
    if not machine:
        error(f"{t('machine_not_found')}: {name}")
        return

    fields = [
        ("name", machine.name, str),
        ("host", machine.host, str),
        ("port", str(machine.port), int),
        ("user", machine.user, str),
    ]

    choices = [
        questionary.Choice(f"{k} = {v}", value=k)
        for k, v, _ in fields
    ]
    choices.append(questionary.Choice(t("config_return"), value="__back__"))

    field_map = {k: (v, tp) for k, v, tp in fields}

    while True:
        field = questionary.select(t("config_edit_machine"), choices=choices).ask()
        if not field or field == "__back__":
            break

        old_val, tp = field_map[field]
        new_val = questionary.text(
            f"{field} [{t('config_edit_prompt')}]",
            default=old_val,
        ).ask()

        if new_val is None or new_val == old_val:
            info(t("config_no_change"))
            continue

        try:
            converted = tp(new_val)
            setattr(machine, field, converted)
            field_map[field] = (new_val, tp)
            for i, (k, _, _) in enumerate(fields):
                if k == field:
                    choices[i] = questionary.Choice(
                        f"{k} = {new_val}", value=k
                    )
                    break
            config.save()
            success(f"{name}.{field}: {old_val} → {new_val}")
        except (ValueError, TypeError) as e:
            error(str(e))


def _interactive_cache(ctx):
    """Interactive cache management"""
    import questionary
    from rich.table import Table

    from .display import console
    from .downloader import cache_dir, clean_cache, list_cache

    config = ctx.obj["config"]
    entries = list_cache(config.settings)

    if entries:
        table = Table(title=t("cache_title"))
        table.add_column(t("cache_col_version"), style="cyan")
        table.add_column(t("cache_col_platform"), style="white")
        table.add_column(t("cache_col_size"), style="white")
        for e in entries:
            table.add_row(e["version"], e["platform"], f"{e['size_mb']}MB")
        console.print(table)
        total_mb = sum(e["size_mb"] for e in entries)
        console.print(f"\n  {len(entries)} {t('cache_total')} {total_mb:.1f}MB\n")
    else:
        info(t("cache_empty"))

    action = questionary.select(
        t("cache_action"),
        choices=[
            t("cache_clean_keep"),
            t("cache_clean_all"),
            questionary.Separator(),
            t("config_return"),
        ],
    ).ask()

    if action == t("cache_clean_keep"):
        clean_cache(config.settings, keep=3)
    elif action == t("cache_clean_all"):
        import shutil
        cache_path = cache_dir(config.settings)
        if cache_path.exists():
            shutil.rmtree(cache_path)
            success(t("cache_all_cleared"))


def _interactive_update(config: Config):
    """Interactive main flow: Scan → Select → Download → Deploy"""
    from .deployer import deploy_all
    from .downloader import download_binary, get_latest_version, verify_checksum
    from .history import record_batch
    from .scanner import scan_all
    from .selector import select_machines

    header(f"{t('app_title')}  {get_version_display()}")

    try:
        target_version = get_latest_version(config.settings)
    except DownloadError as e:
        error(str(e))
        return
    success(f"{t('latest_version')}: {target_version}")

    info(t("scanning"))
    scan_results = scan_all(config.machines, config.settings, local=config.local)
    success(t("scan_done"))

    selected = select_machines(scan_results, target_version)
    if not selected:
        warn(t("no_selection"))
        return

    to_update = [r for r in selected if r["version"] != target_version]
    to_skip = [r for r in selected if r["version"] == target_version]

    if not to_update:
        success(t("all_latest"))
        return

    info(t("update_summary", update=len(to_update), skip=len(to_skip)))

    import tempfile
    with tempfile.TemporaryDirectory(prefix="claude-update-") as tmp_dir:
        binary_path = f"{tmp_dir}/claude"
        try:
            download_binary(config.settings, target_version, binary_path)
            verify_checksum(config.settings, target_version, binary_path)
        except DownloadError as e:
            error(str(e))
            return
        results = deploy_all(selected, binary_path, target_version, config.settings,
                              local=config.local)
        record_batch(results)

    from .display import show_update_results
    show_update_results(results)


# ── scan subcommand ──────────────────────────────────────────────────────────────
@cli.command()
@click.pass_context
def scan(ctx):
    """Scan all machines' Claude Code versions"""
    from .scanner import scan_all

    config = ctx.obj["config"]
    header(t("scan_title"))

    from .downloader import get_latest_version
    try:
        target_version = get_latest_version(config.settings)
    except DownloadError as e:
        error(str(e))
        sys.exit(1)

    results = scan_all(config.machines, config.settings, local=config.local)
    show_scan_results(results, target_version)


# ── update subcommand ────────────────────────────────────────────────────────────
@cli.command()
@click.option("--all", "update_all", is_flag=True, help="Update all machines")
@click.option("--machines", "-m", default=None,
              help="Machine names (comma-separated)")
@click.option("--version", "-v", "target_version", default=None,
              help="Target version")
@click.option("--dry-run", is_flag=True, help="Check only, no update")
@click.option("--no-local", is_flag=True, help="Skip local machine")
@click.pass_context
def update(ctx, update_all, machines, target_version, dry_run, no_local):
    """Execute update"""
    from .deployer import deploy_all
    from .display import show_update_results
    from .downloader import download_binary, get_latest_version, verify_checksum
    from .history import record_batch
    from .scanner import scan_all
    from .selector import select_machines

    config = ctx.obj["config"]
    header(f"{t('app_title')}  {get_version_display()}")

    if target_version:
        info(f"{t('specify_version')}: {target_version}")
    else:
        try:
            target_version = get_latest_version(config.settings)
        except DownloadError as e:
            error(str(e))
            sys.exit(1)
        success(f"{t('latest_version')}: {target_version}")

    if machines:
        names = [n.strip() for n in machines.split(",")]
        target_machines = [m for m in config.machines if m.name in names]
        if not target_machines:
            error(f"{t('machine_not_found')}: {machines}")
            sys.exit(1)
    else:
        target_machines = config.machines

    info(t("scanning"))
    local_cfg = None if no_local else config.local
    scan_results = scan_all(target_machines, config.settings, local=local_cfg)
    show_scan_results(scan_results, target_version)

    selected = scan_results if update_all else select_machines(scan_results, target_version)

    if not selected:
        warn(t("no_selection"))
        return

    to_update = [r for r in selected if r["version"] != target_version]
    if not to_update:
        success(t("all_latest"))
        return

    if dry_run:
        warn(t("dry_run"))
        info(f"{t('will_update')} {len(to_update)} {t('machines')}")
        return

    info(f"{t('will_update')} {len(to_update)} {t('machines')}")

    import tempfile
    with tempfile.TemporaryDirectory(prefix="claude-update-") as tmp_dir:
        binary_path = f"{tmp_dir}/claude"
        try:
            download_binary(config.settings, target_version, binary_path)
            verify_checksum(config.settings, target_version, binary_path)
        except DownloadError as e:
            error(str(e))
            sys.exit(1)
        results = deploy_all(selected, binary_path, target_version, config.settings,
                              local=local_cfg)
        record_batch(results)

    show_update_results(results)


# ── history subcommand ───────────────────────────────────────────────────────────
@cli.command()
@click.option("--machine", "-m", default=None, help="Filter by machine name")
@click.option("--limit", "-n", default=50, help="Number of records")
@click.pass_context
def history(ctx, machine, limit):
    """View update history"""
    from .display import show_history_table
    from .history import get_history

    config = ctx.obj["config"]
    host = None
    if machine:
        m = config.find_machine(machine)
        if m:
            host = m.host
    records = get_history(machine=machine, host=host, limit=limit)
    if not records:
        info(t("no_history"))
        return
    show_history_table(records)


# ── config subcommand group ──────────────────────────────────────────────────────
@cli.group()
@click.pass_context
def config_cmd(ctx):
    """Manage configuration"""
    pass


cli.add_command(config_cmd, "config")


@config_cmd.command("show")
@click.pass_context
def config_show(ctx):
    """Show current configuration"""
    from .display import show_config_panels

    config = ctx.obj["config"]
    show_config_panels(config)


@config_cmd.command("init")
@click.option("--force", "-f", is_flag=True, help="Overwrite existing config")
@click.pass_context
def config_init(ctx, force):
    """Initialize configuration file"""
    import questionary

    config_path = Config.default_config_path()

    if config_path.exists() and not force:
        info(f"{t('config_init_exists')} {config_path}")
        return

    config = Config.create_default(str(config_path))
    success(f"{t('config_init_created')}: {config_path}")

    if sys.stdin.isatty():
        add = questionary.confirm(t("config_init_prompt"), default=True).ask()
        if add:
            name = questionary.text(t("input_name")).ask()
            host = questionary.text(t("input_host")).ask()
            if name and host:
                port = questionary.text(t("input_port"), default="22").ask()
                user = questionary.text(t("input_user"), default="root").ask()
                try:
                    port_val = int(port or 22)
                    if not (1 <= port_val <= 65535):
                        raise ValueError
                except ValueError:
                    error(t("invalid_port", port=port))
                    return
                machine = Machine(name=name, host=host, port=port_val,
                                  user=user or "root")
                config.add_machine(machine)
                config.save()
                success(f"{t('machine_added')}: {name} ({host}:{port_val})")


@config_cmd.command("add-machine")
@click.option("--name", "-n", required=True, help="Machine name")
@click.option("--host", "-h", required=True, help="Host address")
@click.option("--port", "-p", default=22, help="SSH port")
@click.option("--user", "-u", default="root", help="SSH user")
@click.pass_context
def config_add_machine(ctx, name, host, port, user):
    """Add a new machine"""
    config = ctx.obj["config"]
    machine = Machine(name=name, host=host, port=port, user=user)
    try:
        config.add_machine(machine)
        config.save()
        success(f"{t('machine_added')}: {name} ({host}:{port})")
    except ValueError as e:
        error(str(e))


@config_cmd.command("rm-machine")
@click.argument("name")
@click.pass_context
def config_rm_machine(ctx, name):
    """Remove a machine"""
    config = ctx.obj["config"]
    if config.remove_machine(name):
        config.save()
        success(f"{t('machine_removed')}: {name}")
    else:
        error(f"{t('machine_not_found')}: {name}")


# ── cache subcommand group ──────────────────────────────────────────────────────
@cli.group()
@click.pass_context
def cache(ctx):
    """Manage local binary cache"""
    pass


@cache.command("list")
@click.pass_context
def cache_list(ctx):
    """List local cache"""
    from rich.table import Table

    from .display import console
    from .downloader import list_cache

    config = ctx.obj["config"]
    entries = list_cache(config.settings)

    if not entries:
        info(t("cache_empty"))
        return

    table = Table(title=t("cache_title"))
    table.add_column(t("cache_col_version"), style="cyan")
    table.add_column(t("cache_col_platform"), style="white")
    table.add_column(t("cache_col_size"), style="white")
    table.add_column(t("cache_col_path"), style="dim")

    for e in entries:
        table.add_row(e["version"], e["platform"],
                      f"{e['size_mb']}MB", e["path"])

    console.print(table)
    total_mb = sum(e["size_mb"] for e in entries)
    console.print(f"\n  {len(entries)} {t('cache_total')} {total_mb:.1f}MB\n")


@cache.command("clean")
@click.option("--keep", "-k", default=3, help="Keep latest N versions")
@click.option("--all", "clean_all", is_flag=True, help="Clear all cache")
@click.pass_context
def cache_clean(ctx, keep, clean_all):
    """Clean local cache"""
    from .downloader import clean_cache

    config = ctx.obj["config"]

    if clean_all:
        import shutil

        from .downloader import cache_dir
        cache_path = cache_dir(config.settings)
        if cache_path.exists():
            shutil.rmtree(cache_path)
            success(t("cache_all_cleared"))
        else:
            info(t("cache_dir_not_exist"))
        return

    clean_cache(config.settings, keep=keep)
