"""Click CLI definitions"""

import sys

import click
from prompt_toolkit.keys import Keys

from . import __version__, get_version_display
from .config import DEFAULTS, Config, Machine, _shorten_path
from .display import _prefix, console, error, header, info, show_scan_results, success, warn
from .downloader import DownloadError
from .history import (
    EVENT_PIN,
    EVENT_UNPIN,
    has_recent_pin,
    latest_pin,
    record_event,
)
from .i18n import get_lang, set_lang, t
from .scanner import list_installed_versions_local, list_installed_versions_remote


def _bind_esc(question):
    """Add ESC key binding to a questionary Question, making ESC behave like Ctrl+C.

    questionary wraps the underlying prompt_toolkit key_bindings in a
    _MergedKeyBindings that doesn't expose .add() directly. We create
    a fresh KeyBindings with our ESC handler and merge it into the
    application's existing key_bindings.
    """
    from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
    extra = KeyBindings()

    @extra.add(Keys.Escape, eager=True)
    def _on_esc(event):
        event.app.exit(exception=KeyboardInterrupt, style="class:aborting")

    question.application.key_bindings = merge_key_bindings(
        [question.application.key_bindings, extra]
    )
    return question


def _select(message, instruction=None, **kwargs):
    """questionary.select with ESC key bound (ESC returns None) and
    an instruction line under the prompt explaining how to back out.

    Pass instruction=None to suppress (e.g. for top-level menus that
    use ESC for a different purpose like quit). Default is
    t("instruction_back") — "Press ESC to go back".
    """
    import questionary
    if instruction is None:
        instruction = t("instruction_back")
    return _bind_esc(questionary.select(message, instruction=instruction, **kwargs))


def _confirm(message, instruction=None, **kwargs):
    """questionary.confirm with ESC key bound (ESC returns None)"""
    import questionary
    return _bind_esc(questionary.confirm(message, instruction=instruction, **kwargs))


def _text(message, instruction=None, **kwargs):
    """questionary.text with ESC key bound (ESC returns None).

    No default instruction: ESC cancels the current input rather than
    navigating to a 'previous page', so a 'Press ESC to go back' hint
    would be misleading mid-flow (e.g. while filling in name/host/port/
    user for a new machine). Pass instruction explicitly if a hint is
    wanted.
    """
    import questionary
    return _bind_esc(questionary.text(message, instruction=instruction, **kwargs))


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
        action = _select(
            t("menu_prompt"),
            instruction=t("instruction_quit"),
            choices=[
                questionary.Choice(t("menu_scan"), value="scan"),
                questionary.Choice(t("menu_update"), value="update"),
                questionary.Choice(t("menu_rollback"), value="rollback"),
                questionary.Choice(t("menu_history"), value="history"),
                questionary.Choice(t("menu_config"), value="config"),
                questionary.Choice(t("menu_cache"), value="cache"),
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
            elif action == "rollback":
                _interactive_rollback(ctx)
            elif action == "history":
                _interactive_history(ctx)
            elif action == "config":
                _interactive_config(ctx)
            elif action == "cache":
                _interactive_cache(ctx)
        except KeyboardInterrupt:
            console.print()
            continue


def _save_machine_ids(config: Config, scan_results: list[dict]):
    """Auto-save discovered machine-ids to config and backfill history"""
    from .history import EVENT_FIRST_SEEN, backfill_machine_id, record_event

    changed = False
    for r in scan_results:
        mid = r.get("machine_id", "")
        if not mid:
            continue
        machine = config.find_machine(r["name"])
        if machine and not machine.machine_id:
            machine.machine_id = mid
            changed = True
            info(f"{_prefix(r['name'])}{t('machine_id_saved')}")
            backfill_machine_id(r["name"], r["host"], mid)
            record_event(EVENT_FIRST_SEEN, machine_name=machine.name,
                         machine_host=machine.host, machine_id=mid)
    if changed:
        config.save()


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

    _save_machine_ids(config, results)


def _interactive_rollback(ctx):
    """Interactive rollback"""
    import questionary

    from .deployer import rollback_all
    from .history import get_history, record_rollback
    from .scanner import list_installed_versions_local, list_installed_versions_remote

    config = ctx.obj["config"]
    header(t("rollback_title"))

    # Build machine choices
    machine_choices = []
    if config.local.enabled:
        machine_choices.append(questionary.Choice("localhost", value="local"))
    for m in config.machines:
        machine_choices.append(questionary.Choice(m.name, value=m.name))

    if not machine_choices:
        info(t("no_machines"))
        return

    machine_choice = _select(
        t("rollback_select_machine"), choices=machine_choices,
    ).ask()
    if not machine_choice:
        return

    # Get current version and installed versions
    if machine_choice == "local":
        from .scanner import scan_local
        scan_result = scan_local(config.local)
        current_version = scan_result["version"]
        versions = list_installed_versions_local(config.local)
        target_machine = None
    else:
        target_machine = config.find_machine(machine_choice)
        if not target_machine:
            error(f"{t('machine_not_found')}: {machine_choice}")
            return
        from .scanner import scan_machine
        scan_result = scan_machine(target_machine, config.settings)
        current_version = scan_result["version"]
        versions = list_installed_versions_remote(target_machine, config.settings)

    # Filter out current version
    available = [v for v in versions if v != current_version]
    if not available:
        info(t("rollback_no_versions"))
        return

    # Find previous version from history
    machine_id = scan_result.get("machine_id", "")
    host = scan_result.get("host", "")
    # machine_choice is the questionary internal value ("local" or machine name);
    # but records use "localhost" as the local machine name. Map here.
    history_machine = "localhost" if machine_choice == "local" else machine_choice
    history_records = get_history(
        machine_id=machine_id or None,
        machine=history_machine, host=host, limit=50,
    )
    prev_version = None
    for r in history_records:
        if (r.get("event_type") in ("update", "install", "rollback")
                and r.get("to_version") == current_version and r.get("from_version")):
            prev_version = r["from_version"]
            break

    # Build version choices
    version_choices = []
    if prev_version and prev_version in available:
        version_choices.append(
            questionary.Choice(t("rollback_to_previous", version=prev_version), value=prev_version))
    for v in available:
        version_choices.append(questionary.Choice(v, value=v))

    target_version = _select(
        t("rollback_select_version"), choices=version_choices,
    ).ask()
    if not target_version:
        return

    if target_version == current_version:
        info(t("rollback_already"))
        return

    # Confirm
    confirm = _confirm(
        t("rollback_confirm", name=machine_choice, current=current_version, target=target_version),
        default=False,
    ).ask()
    if not confirm:
        return

    # Execute rollback
    scan_result["version"] = current_version
    targets = [scan_result]

    results = rollback_all(
        targets, target_version, config.settings,
        local=config.local if machine_choice == "local" else None,
    )

    for r in results:
        if r["status"] == "success":
            record_rollback(
                machine_name=r["name"], machine_host=r["host"],
                from_version=r["from_version"], to_version=r["to_version"],
                status="success", machine_id=r.get("machine_id", ""),
                duration_seconds=r.get("duration_seconds", 0),
            )
        elif r["status"] == "failed":
            record_rollback(
                machine_name=r["name"], machine_host=r["host"],
                from_version=r["from_version"], to_version=r["to_version"],
                status="failed", machine_id=r.get("machine_id", ""),
                detail=r.get("detail", ""),
                duration_seconds=r.get("duration_seconds", 0),
            )
            error(t("rollback_failed", detail=r.get("detail", "")))

    from .display import show_update_results
    show_update_results(results)


def _interactive_history(ctx):
    """Interactive history"""

    from .display import show_oplog_table
    from .history import get_history

    config = ctx.obj["config"]
    machine_names = [m.name for m in config.machines]
    machine_ids = {m.name: m.machine_id for m in config.machines}
    machine_hosts = {m.name: m.host for m in config.machines}

    # Include localhost if local is enabled
    choices = [t("all_machines")]
    if config.local.enabled:
        choices.append("localhost")
    choices += machine_names

    filter_choice = _select(
        t("oplog_filter"),
        choices=choices,
    ).ask()

    if filter_choice is None:
        return
    elif filter_choice == t("all_machines"):
        machine_id = None
        machine = None
        host = None
    elif filter_choice == "localhost":
        from .scanner import _read_local_machine_id
        machine_id = _read_local_machine_id()
        machine = "localhost"
        host = "127.0.0.1"
    else:
        machine_id = machine_ids.get(filter_choice)
        machine = filter_choice
        host = machine_hosts.get(filter_choice)

    records = get_history(machine_id=machine_id, machine=machine, host=host, limit=50)

    if not records:
        info(t("oplog_no_records"))
    else:
        show_oplog_table(records)


def _interactive_config(ctx):
    """Interactive config management"""
    import questionary

    from .display import show_config_panels

    config = ctx.obj["config"]

    while True:
        show_config_panels(config)

        action = _select(
            t("config_action"),
            choices=[
                t("config_edit_settings"),
                t("config_edit_local"),
                t("config_edit_machine"),
                t("config_add"),
                t("config_remove"),
                t("config_set_lang"),
            ],
        ).ask()

        if action is None:
            break

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

            lang_choice = _select(
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
            name = _text(t("input_name")).ask()
            if not name:
                continue
            host = _text(t("input_host")).ask()
            if not host:
                continue
            port = _text(t("input_port"), default="22").ask()
            user = _text(t("input_user"), default="root").ask()

            try:
                port_val = int(port or 22)
                if not (1 <= port_val <= 65535):
                    raise ValueError
            except ValueError:
                error(t("invalid_port", port=port))
                continue
            machine = Machine(name=name, host=host, port=port_val,
                              user=user or "root")
            try:
                config.add_machine(machine)
                config.save()
                from .history import EVENT_ADD, record_event
                record_event(EVENT_ADD, machine_name=name, machine_host=host)
                success(f"{t('machine_added')}: {name} ({host}:{port})")
            except ValueError as e:
                error(str(e))

        elif action == t("config_remove"):
            machine_names = [m.name for m in config.machines]
            if not machine_names:
                info(t("no_machines"))
                continue
            remove_choices = machine_names
            name = _select(t("select_remove"), choices=remove_choices).ask()
            if name:
                m = config.find_machine(name)
                if config.remove_machine(name):
                    if m:
                        from .history import EVENT_REMOVE, record_event
                        record_event(EVENT_REMOVE, machine_name=name,
                                     machine_host=m.host, machine_id=m.machine_id or "")
                    config.save()
                    success(f"{t('machine_removed')}: {name}")


def _edit_settings(config):
    """Interactive global settings editor"""
    import questionary


    s = config.settings
    fields = [
        ("max_versions", str(s.max_versions), int, "3"),
        ("max_cache_versions", str(s.max_cache_versions), int, "3"),
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
        ("pin_dedup_days", str(s.pin_dedup_days), int, "30"),
    ]

    choices = [
        questionary.Choice(f"{k} = {v}  (default: {d})", value=k)
        for k, v, _, d in fields
    ]

    field_map = {k: (v, tp) for k, v, tp, _ in fields}

    while True:
        field = _select(t("config_edit_settings"), choices=choices).ask()
        if not field:
            break

        old_val, tp = field_map[field]
        new_val = _text(
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

    field_map = {k: (v, tp) for k, v, tp in fields}

    while True:
        field = _select(t("config_edit_local"), choices=choices).ask()
        if not field:
            break

        old_val, tp = field_map[field]
        new_val = _text(
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
    name = _select(t("select_edit_machine"), choices=machine_names).ask()
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

    field_map = {k: (v, tp) for k, v, tp in fields}

    while True:
        field = _select(t("config_edit_machine"), choices=choices).ask()
        if not field:
            break

        old_val, tp = field_map[field]
        new_val = _text(
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

            # Record rename / IP change events
            if field == "name" and old_val != new_val:
                from .history import EVENT_RENAME, record_event
                record_event(EVENT_RENAME, machine_name=new_val,
                             machine_host=machine.host,
                             machine_id=machine.machine_id or "",
                             old_name=old_val)
            elif field == "host" and old_val != new_val:
                from .history import EVENT_IP_CHANGE, record_event
                record_event(EVENT_IP_CHANGE, machine_name=machine.name,
                             machine_host=new_val,
                             machine_id=machine.machine_id or "",
                             old_host=old_val)
        except (ValueError, TypeError) as e:
            error(str(e))


def _interactive_cache(ctx):
    """Interactive cache management"""
    from rich.table import Table

    from .display import console
    from .downloader import cache_dir, clean_cache, list_cache

    config = ctx.obj["config"]

    while True:
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

        action = _select(
            t("cache_action"),
            choices=[
                t("cache_clean_keep_n", n=config.settings.max_cache_versions),
                t("cache_clean_all"),
            ],
        ).ask()

        if action is None:
            break

        if action == t("cache_clean_keep_n", n=config.settings.max_cache_versions):
            clean_cache(config.settings)
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

    _save_machine_ids(config, scan_results)

    selected = select_machines(scan_results, target_version)
    if selected is None:
        # ESC pressed — silent back-out to previous screen
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
            # download_binary returns the path to the usable binary
            # (cache path on hit, output_path on miss)
            binary_path = download_binary(config.settings, target_version, binary_path)
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
    _save_machine_ids(config, results)


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

    if selected is None:
        # ESC in interactive selector — silent back-out
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
            # download_binary returns the path to the usable binary
            # (cache path on hit, output_path on miss)
            binary_path = download_binary(config.settings, target_version, binary_path)
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
@click.option("--type", "-t", "event_type", default=None,
              type=click.Choice([
                  "update", "install", "rollback", "add", "remove",
                  "rename", "ip_change", "first_seen"]),
              help="Filter by event type")
@click.option("--limit", "-n", default=50, help="Number of records")
@click.pass_context
def history(ctx, machine, event_type, limit):
    """View operation log"""
    from .display import show_oplog_table
    from .history import get_history

    config = ctx.obj["config"]
    host = None
    machine_id = None
    if machine:
        m = config.find_machine(machine)
        if m:
            host = m.host
            machine_id = m.machine_id
    records = get_history(machine_id=machine_id, machine=machine, host=host,
                          event_type=event_type, limit=limit)
    if not records:
        info(t("oplog_no_records"))
        return
    show_oplog_table(records)


# ── rollback subcommand ────────────────────────────────────────────────────────
@cli.command()
@click.option("--machine", "-m", default=None, help="Machine name")
@click.option("--version", "-v", "target_version", default=None,
              help="Target version to rollback to (default: previous version)")
@click.option("--all", "rollback_all_flag", is_flag=True, help="Rollback all machines")
@click.pass_context
def rollback(ctx, machine, target_version, rollback_all_flag):
    """Rollback to a previous version"""
    from .deployer import rollback_all as do_rollback
    from .history import record_rollback
    from .scanner import list_installed_versions_remote, scan_machine

    config = ctx.obj["config"]
    header(t("rollback_title"))

    # Determine which machines to rollback
    if machine:
        m = config.find_machine(machine)
        if not m:
            error(f"{t('machine_not_found')}: {machine}")
            sys.exit(1)
        machines_to_rollback = [m]
    elif rollback_all_flag:
        machines_to_rollback = config.machines
    else:
        error(t("specify_machine_or_all"))
        sys.exit(1)

    results = []
    for m in machines_to_rollback:
        scan_result = scan_machine(m, config.settings)
        current_version = scan_result["version"]
        if not target_version:
            prev = _find_previous_version(config, m.name, m.host,
                                          m.machine_id or "", current_version)
            if not prev:
                error(f"{t('rollback_no_versions')}: {m.name}")
                continue
            target_ver = prev
        else:
            target_ver = target_version

        available = list_installed_versions_remote(m, config.settings)
        if target_ver not in available:
            error(t("version_not_on_machine", name=m.name, version=target_ver))
            continue

        scan_result["version"] = current_version
        r = do_rollback([scan_result], target_ver, config.settings,
                        local=config.local)
        results.extend(r)

    # Record rollback events
    for r in results:
        if r["status"] in ("success", "failed"):
            record_rollback(
                machine_name=r["name"], machine_host=r["host"],
                from_version=r["from_version"], to_version=r["to_version"],
                status=r["status"], machine_id=r.get("machine_id", ""),
                detail=r.get("detail", ""),
                duration_seconds=r.get("duration_seconds", 0),
            )

    from .display import show_update_results
    show_update_results(results)


def _find_previous_version(config, name, host, machine_id, current_version=""):
    """Find the previous version from history for a given machine.

    Matches history records whose `to_version` equals `current_version` (the
    machine's currently-installed version), and returns that record's
    `from_version`. This is the "version that was running before the
    machine arrived at `current_version`".

    If no `current_version` is given (or no record matches), returns the
    `from_version` of the most recent relevant record as a fallback.
    """
    from .history import get_history
    records = get_history(
        machine_id=machine_id or None, machine=name, host=host, limit=50,
    )
    # Preferred: most recent record whose to_version matches the current version
    for r in records:
        if (r.get("event_type") in ("update", "install", "rollback")
                and r.get("to_version")
                and r.get("to_version") == current_version
                and r.get("from_version")):
            return r.get("from_version", "")
    # Fallback: most recent record with any from_version
    for r in records:
        if (r.get("event_type") in ("update", "install", "rollback")
                and r.get("from_version")):
            return r.get("from_version", "")
    return None


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
    config_path = Config.default_config_path()

    if config_path.exists() and not force:
        info(f"{t('config_init_exists')} {config_path}")
        return

    config = Config.create_default(str(config_path))
    success(f"{t('config_init_created')}: {config_path}")

    if sys.stdin.isatty():
        add = _confirm(t("config_init_prompt"), default=True).ask()
        if add:
            name = _text(t("input_name")).ask()
            host = _text(t("input_host")).ask()
            if name and host:
                port = _text(t("input_port"), default="22").ask()
                user = _text(t("input_user"), default="root").ask()
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
        from .history import EVENT_ADD, record_event
        record_event(EVENT_ADD, machine_name=name, machine_host=host)
        success(f"{t('machine_added')}: {name} ({host}:{port})")
    except ValueError as e:
        error(str(e))


@config_cmd.command("rm-machine")
@click.argument("name")
@click.pass_context
def config_rm_machine(ctx, name):
    """Remove a machine"""
    config = ctx.obj["config"]
    m = config.find_machine(name)
    if config.remove_machine(name):
        if m:
            from .history import EVENT_REMOVE, record_event
            record_event(EVENT_REMOVE, machine_name=name,
                         machine_host=m.host, machine_id=m.machine_id or "")
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
@click.option("--keep", "-k", default=None, type=int,
              help="Keep latest N versions (default: from config)")
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


# ── backfill subcommand ────────────────────────────────────────────────────────
@cli.command("backfill-events")
@click.pass_context
def backfill_events(ctx):
    """Backfill rename/first_seen events from existing history"""
    from .history import backfill_events as do_backfill
    do_backfill()
    success(t("backfill_complete"))


# ── pin / unpin subcommands ────────────────────────────────────────────────────
@cli.command()
@click.option("--machine", required=True, help=t("cli_help_machine"))
@click.option("--version", "target_version", required=True, help=t("cli_help_pin_version"))
@click.option("--force", is_flag=True, default=False,
              help=t("cli_help_pin_force"))
@click.pass_context
def pin(ctx, machine, target_version, force):
    """Manually mark a (machine, version) pair as a known-good pin."""
    config = ctx.obj["config"]
    m = config.find_machine(machine)
    if not m:
        error(t("pin_no_such_machine", name=machine))
        sys.exit(1)

    # Validate version is installed
    is_local = (m.name == "localhost" or m.host == "127.0.0.1")
    if is_local:
        installed = list_installed_versions_local(config.local)
    else:
        installed = list_installed_versions_remote(m, config.settings)
    if target_version not in installed:
        error(t("pin_version_missing", name=machine, version=target_version))
        sys.exit(1)

    machine_id = m.machine_id or ""
    if not force and has_recent_pin(machine_id, target_version,
                                    days=config.settings.pin_dedup_days):
        info(t("pin_already_recent", machine=machine, version=target_version,
               days=config.settings.pin_dedup_days))
        return

    record_event(
        EVENT_PIN,
        machine_name=m.name,
        machine_host=m.host,
        machine_id=machine_id,
        version=target_version,
    )
    success(t("pin_recorded", machine=machine, version=target_version))


@cli.command()
@click.option("--machine", required=True, help=t("cli_help_machine"))
@click.option("--version", "target_version", required=True, help=t("cli_help_unpin_version"))
@click.pass_context
def unpin(ctx, machine, target_version):
    """Remove the most-recent pin record for a (machine, version) pair."""
    config = ctx.obj["config"]
    m = config.find_machine(machine)
    if not m:
        error(t("pin_no_such_machine", name=machine))
        sys.exit(1)

    machine_id = m.machine_id or ""
    current = latest_pin(machine_id, target_version)
    if current is None:
        error(t("unpin_no_record", name=machine, version=target_version))
        sys.exit(1)
    if current.get("event_type") == EVENT_UNPIN:
        # Already unpinned — no-op
        info(t("unpin_already", name=machine, version=target_version))
        return

    record_event(
        EVENT_UNPIN,
        machine_name=m.name,
        machine_host=m.host,
        machine_id=machine_id,
        version=target_version,
    )
    success(t("unpin_recorded", machine=machine, version=target_version))
