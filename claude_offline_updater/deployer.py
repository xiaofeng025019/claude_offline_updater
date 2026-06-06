"""Deployment module (local + remote)"""

import contextlib
import logging
import os
import re
import shlex
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import paramiko

from . import history
from .cleaner import cleanup_local_versions, cleanup_old_versions
from .config import LocalConfig, Settings
from .display import _prefix, info, success, warn
from .i18n import t

# Suppress paramiko's noisy transport-level logging
logging.getLogger("paramiko").setLevel(logging.CRITICAL)


def deploy_local(
    result: dict,
    binary_path: str,
    target_version: str,
    local: LocalConfig,
    settings: Settings,
) -> dict:
    """Deploy to local machine"""
    current_ver = result["version"]
    start_time = time.time()

    base_result = {
        "name": result["name"],
        "host": result["host"],
        "from_version": current_ver,
        "to_version": target_version,
        "machine_id": result.get("machine_id", ""),
    }

    if current_ver == target_version:
        return {**base_result, "status": "skipped", "duration_seconds": 0}

    info(f"{_prefix('localhost')}{t('deploy_local')}")

    # Record current symlink target for rollback
    claude_bin_path = os.path.expanduser(local.claude_bin)
    rollback_target = None
    if os.path.islink(claude_bin_path):
        rollback_target = os.path.realpath(claude_bin_path)

    # Try official install
    install_ok = False
    try:
        proc = subprocess.run(
            [binary_path, "install"],
            capture_output=True, text=True, timeout=60,
        )
        if proc.returncode == 0:
            install_ok = True
    except Exception:
        pass

    # fallback: local manual deployment
    if not install_ok:
        info(f"{_prefix('localhost')}{t('deploy_offline')}")
        versions_dir = os.path.expanduser(local.versions_dir)
        claude_bin = os.path.expanduser(local.claude_bin)

        try:
            os.makedirs(versions_dir, exist_ok=True)
            os.makedirs(os.path.dirname(claude_bin), exist_ok=True)

            target_path = os.path.join(versions_dir, target_version)
            # Skip copy if target already exists and is executable
            if not (os.path.isfile(target_path) and os.access(target_path, os.X_OK)):
                shutil.copy2(binary_path, target_path)
                os.chmod(target_path, 0o755)
                info(f"{_prefix('localhost')}{t('cached_to')} {target_path}")
            else:
                info(f"{_prefix('localhost')}{t('skipping_copy_cached', version=target_version)}")

            # Update symlink
            if os.path.islink(claude_bin) or os.path.exists(claude_bin):
                os.remove(claude_bin)
            os.symlink(target_path, claude_bin)

            _set_install_method_local()
        except Exception as e:
            return {**base_result, "status": "failed",
                    "detail": f"{t('deploy_local_failed')}: {e}",
                    "duration_seconds": time.time() - start_time}

    # Verify version
    info(f"{_prefix('localhost')}{t('verifying_version')}")
    claude_bin = os.path.expanduser(local.claude_bin)
    try:
        proc = subprocess.run(
            [claude_bin, "--version"],
            capture_output=True, text=True, timeout=10,
        )
        match = re.search(r'(\d+\.\d+\.\d+)', proc.stdout)
        installed_ver = match.group(1) if match else ""

        if installed_ver != target_version:
            # Verification failed, rollback
            if rollback_target:
                _local_rollback(claude_bin_path, rollback_target)
                warn(f"{_prefix('localhost')}{t('local_rollback')}")
            return {**base_result, "status": "failed",
                    "detail": f"{t('version_verify_fail')}: {installed_ver}",
                    "duration_seconds": time.time() - start_time}
    except Exception as e:
        # Verification exception, rollback
        if rollback_target:
            _local_rollback(claude_bin_path, rollback_target)
            warn(f"{_prefix('localhost')}{t('local_rollback_err')}")
        return {**base_result, "status": "failed",
                "detail": f"{t('verify_failed')}: {e}",
                "duration_seconds": time.time() - start_time}

    # Cleanup old versions
    cleanup_local_versions(local, settings.max_versions, label="localhost")

    success(f"{_prefix('localhost')}{t('update_complete')}: {current_ver} → {target_version}")
    return {**base_result, "status": "success",
            "duration_seconds": time.time() - start_time}


def _local_rollback(claude_bin: str, target: str):
    """Rollback local symlink"""
    try:
        if os.path.islink(claude_bin) or os.path.exists(claude_bin):
            os.remove(claude_bin)
        os.symlink(target, claude_bin)
    except Exception as e:
        warn(f"{_prefix('localhost')}{t('rollback_failed', detail=str(e))}")


def deploy_to_machine(
    result: dict,
    binary_path: str,
    target_version: str,
    settings: Settings,
) -> dict:
    """Deploy to a single remote machine, returns result dict"""
    name = result["name"]
    host = result["host"]
    port = result["port"]
    user = result["user"]
    current_ver = result["version"]
    start_time = time.time()

    base_result = {
        "name": name,
        "host": host,
        "from_version": current_ver,
        "to_version": target_version,
        "machine_id": result.get("machine_id", ""),
    }

    if current_ver == target_version:
        return {**base_result, "status": "skipped", "duration_seconds": 0}

    rollback_target = None
    client = None

    try:
        client = _ssh_connect(host, port, user, settings)

        rollback_target = _get_current_symlink(client, settings.remote_claude_bin)

        # Optimization: if the remote already has this version installed, skip
        # the SCP transfer entirely and go straight to symlink-swap. This
        # is the common case for rollbacks (target version usually exists)
        # and re-deployments after a partial failure.
        if _is_remote_version_installed(
            client, settings.remote_versions_dir, target_version,
        ):
            info(f"{_prefix(name)}{t('skipping_transfer_cached', version=target_version)}")
            # Even though the binary is already on the remote, the symlink
            # at remote_claude_bin may still point to the OLD version. Swap
            # it to the target version before verification.
            vdir = settings.remote_versions_dir
            cbin = settings.remote_claude_bin
            ln_cmd = f"ln -sf {vdir}/{target_version} {cbin}"
            ln_stdin, ln_stdout, ln_stderr = client.exec_command(ln_cmd, timeout=10)
            ln_stdout.channel.recv_exit_status()
        else:
            info(f"{_prefix(name)}{t('transferring')}")
            sftp = client.open_sftp()
            remote_tmp = _resolve_remote_path(client, settings.remote_tmp_dir)
            remote_path = f"{remote_tmp}/claude"
            _ensure_remote_dir(client, remote_tmp)

            try:
                if settings.scp_bandwidth_limit > 0:
                    _scp_with_limit(binary_path, host, port, user,
                                    remote_path, settings.scp_bandwidth_limit, settings)
                else:
                    sftp.put(binary_path, remote_path)
            finally:
                sftp.close()

            client.exec_command(f"chmod +x {shlex.quote(remote_path)}", timeout=10)

            info(f"{_prefix(name)}{t('installing')}")
            install_ok = False
            try:
                stdin, stdout, stderr = client.exec_command(
                    f"{shlex.quote(remote_path)} install", timeout=60,
                )
                if stdout.channel.recv_exit_status() == 0:
                    install_ok = True
            except Exception:
                pass

            if not install_ok:
                info(f"{_prefix(name)}{t('deploy_offline')}")
                # Paths from config are validated shell-safe at load time
                # (config._validate_path_chars), so we pass them unquoted to
                # preserve tilde expansion.
                vdir = settings.remote_versions_dir
                cbin = settings.remote_claude_bin
                rpath = remote_path
                tver = target_version
                deploy_cmd = (
                    f"mkdir -p {vdir} && "
                    f"mkdir -p $(dirname {cbin}) && "
                    f"cp {rpath} {vdir}/{tver} && "
                    f"chmod +x {vdir}/{tver} && "
                    f"ln -sf {vdir}/{tver} {cbin}"
                )
                stdin, stdout, stderr = client.exec_command(deploy_cmd, timeout=30)
                if stdout.channel.recv_exit_status() != 0:
                    return {**base_result, "status": "failed",
                            "detail": t("deploy_failed"),
                            "duration_seconds": time.time() - start_time}

                _ensure_path(client, label=name)
                _set_install_method_remote(client, label=name)

        info(f"{_prefix(name)}{t('verifying_version')}")
        stdin, stdout, stderr = client.exec_command(
            f"{settings.remote_claude_bin} --version 2>/dev/null", timeout=10,
        )
        installed = stdout.read().decode().strip()
        match = re.search(r'(\d+\.\d+\.\d+)', installed)
        installed_ver = match.group(1) if match else ""

        if installed_ver != target_version:
            if rollback_target:
                _rollback_symlink(client, settings.remote_claude_bin, rollback_target, label=name)
                warn(f"{_prefix(name)}{t('remote_rollback')} {rollback_target}")
            return {**base_result, "status": "failed",
                    "detail": f"{t('version_verify_fail')}: {installed_ver}",
                    "duration_seconds": time.time() - start_time}

        cleanup_old_versions(client, settings, label=name)
        client.exec_command(f"rm -rf {settings.remote_tmp_dir}", timeout=10)

        success(f"{_prefix(name)}{t('update_complete')}: {current_ver} → {target_version}")
        return {**base_result, "status": "success",
                "duration_seconds": time.time() - start_time}

    except Exception as e:
        if rollback_target:
            try:
                rollback_client = _ssh_connect(host, port, user, settings)
                try:
                    _rollback_symlink(
                        rollback_client, settings.remote_claude_bin,
                        rollback_target, label=name,
                    )
                    warn(f"{_prefix(name)}{t('deploy_exception_rollback')} {rollback_target}")
                finally:
                    rollback_client.close()
            except Exception:
                pass
        return {**base_result, "status": "failed",
                "detail": str(e),
                "duration_seconds": time.time() - start_time}
    finally:
        if client:
            client.close()


def deploy_all(
    selected: list[dict],
    binary_path: str,
    target_version: str,
    settings: Settings,
    local: LocalConfig | None = None,
) -> list[dict]:
    """Deploy to all selected machines (including local)"""
    results = []

    # Local deployment
    local_items = [r for r in selected if r.get("is_local")]
    remote_items = [r for r in selected if not r.get("is_local")]

    for r in local_items:
        if r["version"] == target_version:
            results.append({
                "name": r["name"], "host": r["host"],
                "from_version": r["version"], "to_version": target_version,
                "machine_id": r.get("machine_id", ""),
                "status": "skipped", "duration_seconds": 0,
            })
        elif local:
            results.append(deploy_local(r, binary_path, target_version, local, settings))

    # Skip already-up-to-date remotes
    for r in remote_items:
        if r["version"] == target_version:
            results.append({
                "name": r["name"], "host": r["host"],
                "from_version": r["version"], "to_version": target_version,
                "machine_id": r.get("machine_id", ""),
                "status": "skipped", "duration_seconds": 0,
            })

    to_update = [r for r in remote_items if r["version"] != target_version]

    if to_update:
        info(f"{t('parallel_deploy')} ({len(to_update)} {t('remote_machines')})...")

        with ThreadPoolExecutor(max_workers=min(settings.max_workers, len(to_update))) as pool:
            futures = {
                pool.submit(deploy_to_machine, r, binary_path, target_version, settings): r
                for r in to_update
            }
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as e:
                    r = futures[future]
                    results.append({
                        "name": r["name"], "host": r["host"],
                        "from_version": r["version"], "to_version": target_version,
                        "machine_id": r.get("machine_id", ""),
                        "status": "failed", "detail": str(e),
                        "duration_seconds": 0,
                    })

    # Sort: local first, remote in original selection order
    def sort_key(r):
        # is_local must be looked up from the original selection (results don't carry it)
        is_local = any(s.get("is_local") and s["name"] == r["name"] for s in selected)
        if is_local:
            return (0, 0)
        name_order = {r2["name"]: i + 1 for i, r2 in enumerate(selected)}
        return (1, name_order.get(r["name"], 999))

    results.sort(key=sort_key)
    return results


def _ssh_connect(host: str, port: int, user: str, settings: Settings) -> paramiko.SSHClient:
    """Establish SSH connection"""
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    with contextlib.suppress(FileNotFoundError):
        client.load_host_keys(os.path.expanduser("~/.ssh/known_hosts"))
    policy = settings.ssh_host_key_policy
    if policy == "auto":
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    elif policy == "reject":
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
    else:
        client.set_missing_host_key_policy(paramiko.WarningPolicy())
    client.connect(host, port=port, username=user, timeout=settings.connect_timeout)
    return client


def _get_current_symlink(client: paramiko.SSHClient, claude_bin: str) -> str | None:
    """Get remote claude symlink target path (for rollback)"""
    try:
        stdin, stdout, stderr = client.exec_command(
            f"readlink -f {claude_bin} 2>/dev/null", timeout=10,
        )
        target = stdout.read().decode().strip()
        return target if target and target != claude_bin else None
    except Exception:
        return None


def _is_remote_version_installed(
    client: paramiko.SSHClient,
    versions_dir: str,
    target_version: str,
) -> bool:
    """Check whether `versions_dir/<target_version>` already exists and is
    executable on the remote. Used to skip SCP when re-deploying a version
    that's already on the remote (saves 10-50 MB of transfer per machine).

    Refuses to run if `target_version` has unsafe characters (defense in
    depth — versions_dir is config-validated, but version comes from CLI).
    """
    if not _is_safe_remote_path(target_version) or not _is_safe_remote_path(versions_dir):
        return False
    try:
        stdin, stdout, stderr = client.exec_command(
            f"test -x {versions_dir}/{target_version} && echo yes || echo no",
            timeout=10,
        )
        out = stdout.read().decode().strip()
        return out == "yes"
    except Exception:
        return False


def _rollback_symlink(client: paramiko.SSHClient, claude_bin: str, target: str, label: str = ""):
    """Rollback symlink to specified target"""
    prefix = _prefix(label)
    try:
        # target comes from `readlink` output (remote-controlled). Refuse
        # to pass unquoted if it has shell metacharacters.
        if not _is_safe_remote_path(target):
            raise ValueError(f"unsafe rollback target: {target!r}")
        stdin, stdout, stderr = client.exec_command(
            f"ln -sf {target} {claude_bin}", timeout=10,
        )
        # Wait for ln -sf to actually complete on the remote before returning
        stdout.channel.recv_exit_status()
    except Exception as e:
        warn(f"{prefix}{t('rollback_symlink_failed', error=e)}")


def _auto_pin_on_rollback(result: dict, pin_dedup_days: int = 30):
    """If rollback was a clean success, write an EVENT_PIN record.
    Independent of any string status convention — single check.
    Silent skip on dedup (auto path is non-interactive).
    Never raises — pin write failure must not mask a successful rollback."""
    if result.get("status") != "success":
        return
    machine_id = result.get("machine_id", "")
    target_version = result.get("to_version", "")
    if not machine_id or not target_version:
        return
    try:
        if history.has_recent_pin(machine_id, target_version, days=pin_dedup_days):
            return
        history.record_event(
            history.EVENT_PIN,
            machine_name=result["name"],
            machine_host=result["host"],
            machine_id=machine_id,
            version=target_version,
        )
    except Exception as e:  # noqa: BLE001 — never let pin failure mask rollback success
        warn(t("auto_pin_failed", prefix=_prefix(result.get('name', '?')), error=e))


def _scp_with_limit(local_path: str, host: str, port: int, user: str,
                     remote_path: str, limit_kbs: int, settings: Settings):
    """Transfer using scp command with bandwidth limit"""
    host_key_opt = _ssh_host_key_option(settings.ssh_host_key_policy)
    cmd = [
        "scp", "-P", str(port),
        "-o", "ConnectTimeout=10",
        "-o", host_key_opt,
        "-l", str(limit_kbs),
        local_path,
        f"{user}@{host}:{remote_path}",
    ]
    proc = subprocess.run(cmd, capture_output=True, timeout=600)
    if proc.returncode != 0:
        raise Exception(t("scp_failed_limit", limit_kbs=limit_kbs))


def _ssh_host_key_option(policy: str) -> str:
    """Map ssh_host_key_policy to SSH option value"""
    if policy == "auto":
        return "StrictHostKeyChecking=accept-new"
    elif policy == "reject":
        return "StrictHostKeyChecking=yes"
    else:  # warn
        return "StrictHostKeyChecking=accept-new"


def _resolve_remote_path(client: paramiko.SSHClient, path: str) -> str:
    """Resolve ~ in remote paths — SFTP doesn't expand tilde, so ask the
    remote shell to expand it. Path must not contain shell metacharacters
    (validated at config load). Returns the original path if no ~ or if
    expansion fails."""
    if not path.startswith("~"):
        return path
    if not _is_safe_remote_path(path):
        return path
    try:
        stdin, stdout, stderr = client.exec_command(
            f"echo {path}", timeout=5,
        )
        resolved = stdout.read().decode().strip()
        return resolved if resolved else path
    except Exception:
        return path


def _is_safe_remote_path(path: str) -> bool:
    """Path contains only chars safe to pass unquoted to a remote shell.

    Tilde expansion requires the path to be passed unquoted (shlex.quote
    would single-quote and suppress expansion). The risk is shell injection
    if a user-supplied path contains `;`, `|`, `$`, etc. Since config paths
    are user-controlled YAML, we whitelist the allowed character set.
    """
    return all(c.isalnum() or c in "/._-~" for c in path)


def _ensure_remote_dir(client: paramiko.SSHClient, path: str):
    """Ensure remote directory exists"""
    client.exec_command(f"mkdir -p {shlex.quote(path)}", timeout=10)


def _ensure_path(client: paramiko.SSHClient, label: str = ""):
    """Ensure ~/.local/bin is in PATH (check .bashrc, add if missing, no duplicates)"""
    prefix = _prefix(label)
    check_cmd = "grep -q '\\.local/bin' ~/.bashrc 2>/dev/null; echo $?"
    stdin, stdout, stderr = client.exec_command(check_cmd, timeout=10)
    result = stdout.read().decode().strip()

    if result == "0":
        return

    add_cmd = 'echo \'export PATH="$HOME/.local/bin:$PATH"\' >> ~/.bashrc'
    stdin, stdout, stderr = client.exec_command(add_cmd, timeout=10)
    if stdout.channel.recv_exit_status() == 0:
        info(f"{prefix}{t('path_added')}")
    else:
        warn(f"{prefix}{t('path_add_failed')}")


def _set_install_method_remote(client: paramiko.SSHClient, label: str = ""):
    """Set installMethod to native in remote ~/.claude.json"""
    prefix = _prefix(label)
    # Try python3 → python → node to modify ~/.claude.json
    py_code = (
        'import json,os; '
        'p=os.path.expanduser("~/.claude.json"); '
        'd=json.load(open(p)) if os.path.exists(p) else {}; '
        'd["installMethod"]="native"; '
        'json.dump(d,open(p,"w"),indent=2)'
    )
    node_code = (
        'const p=require("os").homedir()+"/.claude.json"; '
        'const fs=require("fs"); '
        'let d={}; '
        'try{d=JSON.parse(fs.readFileSync(p,"utf8"))}catch(e){} '
        'd.installMethod="native"; '
        'fs.writeFileSync(p,JSON.stringify(d,null,2))'
    )
    set_cmd = (
        f'python3 -c \'{py_code}\' 2>/dev/null || '
        f'python -c \'{py_code}\' 2>/dev/null || '
        f'node -e \'{node_code}\' 2>/dev/null'
    )
    stdin, stdout, stderr = client.exec_command(set_cmd, timeout=10)
    exit_code = stdout.channel.recv_exit_status()
    if exit_code == 0:
        info(f"{prefix}{t('install_method_set')}")
    else:
        warn(f"{prefix}{t('install_method_set_failed')}")


def _set_install_method_local():
    """Set installMethod to native in local ~/.claude.json"""
    import json
    claude_json = os.path.expanduser("~/.claude.json")

    try:
        if os.path.exists(claude_json):
            with open(claude_json) as f:
                d = json.load(f)
            if d.get("installMethod") == "native":
                return
        else:
            d = {}

        d["installMethod"] = "native"
        with open(claude_json, "w") as f:
            json.dump(d, f, indent=2)
        info(f"{_prefix('localhost')}{t('install_method_set')}")
    except Exception as e:
        warn(f"{_prefix('localhost')}{t('install_method_set_failed')}: {e}")


# ── Rollback ─────────────────────────────────────────────────────────────────

def rollback_local(
    current_version: str,
    target_version: str,
    local: LocalConfig,
    settings: Settings,
    machine_id: str = "",
) -> dict:
    """Rollback local machine to a previous version"""
    start_time = time.time()
    name = "localhost"
    base_result = {
        "name": name, "host": "127.0.0.1",
        "from_version": current_version, "to_version": target_version,
        "machine_id": machine_id,
    }

    if current_version == target_version:
        return {**base_result, "status": "skipped", "duration_seconds": 0}

    claude_bin = os.path.expanduser(local.claude_bin)
    versions_dir = os.path.expanduser(local.versions_dir)
    target_path = os.path.join(versions_dir, target_version)

    # Verify target binary exists
    if not os.path.isfile(target_path) or not os.access(target_path, os.X_OK):
        return {**base_result, "status": "failed",
                "detail": t("version_not_in_local_dir", version=target_version, dir=versions_dir),
                "duration_seconds": time.time() - start_time}

    # Replace symlink atomically via ln -sf
    try:
        subprocess.run(
            ["ln", "-sf", target_path, claude_bin],
            check=True, capture_output=True, timeout=10,
        )
    except Exception as e:
        return {**base_result, "status": "failed",
                "detail": str(e),
                "duration_seconds": time.time() - start_time}

    # Verify version
    try:
        proc = subprocess.run(
            [claude_bin, "--version"],
            capture_output=True, text=True, timeout=10,
        )
        match = re.search(r'(\d+\.\d+\.\d+)', proc.stdout)
        installed_ver = match.group(1) if match else ""

        if installed_ver != target_version:
            # Revert symlink back
            old_path = os.path.join(versions_dir, current_version)
            if os.path.isfile(old_path):
                subprocess.run(
                    ["ln", "-sf", old_path, claude_bin],
                    capture_output=True, timeout=10,
                )
            return {**base_result, "status": "failed",
                    "detail": f"{t('version_verify_fail')}: {installed_ver}",
                    "duration_seconds": time.time() - start_time}
    except Exception as e:
        return {**base_result, "status": "failed",
                "detail": str(e),
                "duration_seconds": time.time() - start_time}

    success(f"{_prefix(name)}{t('rollback_success')}: {current_version} → {target_version}")
    result = {**base_result, "status": "success",
              "duration_seconds": time.time() - start_time}
    _auto_pin_on_rollback(result, pin_dedup_days=settings.pin_dedup_days)
    return result


def rollback_to_machine(
    machine_result: dict,
    target_version: str,
    settings: Settings,
) -> dict:
    """Rollback a remote machine to a previous version"""
    name = machine_result["name"]
    host = machine_result["host"]
    port = machine_result["port"]
    user = machine_result["user"]
    current_version = machine_result["version"]
    machine_id = machine_result.get("machine_id", "")
    start_time = time.time()

    base_result = {
        "name": name, "host": host,
        "from_version": current_version, "to_version": target_version,
        "machine_id": machine_id,
    }

    if current_version == target_version:
        return {**base_result, "status": "skipped", "duration_seconds": 0}

    client = None
    try:
        client = _ssh_connect(host, port, user, settings)

        # Paths are validated shell-safe at config load. Pass unquoted
        # to preserve tilde expansion.
        vdir = settings.remote_versions_dir
        cbin = settings.remote_claude_bin
        tver = target_version

        # Verify target binary exists on remote
        stdin, stdout, stderr = client.exec_command(
            f"test -x {vdir}/{tver} && echo ok || echo missing", timeout=10,
        )
        check = stdout.read().decode().strip()
        if check != "ok":
            return {**base_result, "status": "failed",
                    "detail": t("version_not_on_remote", version=target_version),
                    "duration_seconds": time.time() - start_time}

        # Replace symlink
        stdin, stdout, stderr = client.exec_command(
            f"ln -sf {vdir}/{tver} {cbin}", timeout=10,
        )
        # Wait for ln -sf to actually complete on the remote before verifying
        stdout.channel.recv_exit_status()

        # Verify
        stdin, stdout, stderr = client.exec_command(
            f"{cbin} --version 2>/dev/null", timeout=10,
        )
        output = stdout.read().decode().strip()
        match = re.search(r'(\d+\.\d+\.\d+)', output)
        installed_ver = match.group(1) if match else ""

        if installed_ver != target_version:
            # Revert
            cur_ver = shlex.quote(current_version)
            client.exec_command(
                f"ln -sf {vdir}/{cur_ver} {cbin}", timeout=10,
            )
            return {**base_result, "status": "failed",
                    "detail": f"{t('version_verify_fail')}: {installed_ver}",
                    "duration_seconds": time.time() - start_time}

        success(f"{_prefix(name)}{t('rollback_success')}: {current_version} → {target_version}")
        result = {**base_result, "status": "success",
                  "duration_seconds": time.time() - start_time}
        _auto_pin_on_rollback(result, pin_dedup_days=settings.pin_dedup_days)
        return result

    except Exception as e:
        return {**base_result, "status": "failed",
                "detail": str(e),
                "duration_seconds": time.time() - start_time}
    finally:
        if client:
            client.close()


def rollback_all(
    targets: list[dict],
    target_version: str,
    settings: Settings,
    local: LocalConfig | None = None,
) -> list[dict]:
    """Rollback all selected machines"""
    results = []
    local_items = [r for r in targets if r.get("is_local")]
    remote_items = [r for r in targets if not r.get("is_local")]

    for r in local_items:
        if local:
            results.append(rollback_local(
                r["version"], target_version, local, settings,
                machine_id=r.get("machine_id", ""),
            ))
        else:
            results.append({
                "name": r["name"], "host": r["host"],
                "from_version": r["version"], "to_version": target_version,
                "machine_id": r.get("machine_id", ""),
                "status": "skipped", "duration_seconds": 0,
            })

    if remote_items:
        with ThreadPoolExecutor(max_workers=min(settings.max_workers, len(remote_items))) as pool:
            futures = {
                pool.submit(rollback_to_machine, r, target_version, settings): r
                for r in remote_items
            }
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as e:
                    r = futures[future]
                    results.append({
                        "name": r["name"], "host": r["host"],
                        "from_version": r["version"], "to_version": target_version,
                        "machine_id": r.get("machine_id", ""),
                        "status": "failed", "detail": str(e),
                        "duration_seconds": 0,
                    })

    def sort_key(r):
        # is_local must be looked up from the original target (results don't carry it)
        is_local = any(t.get("is_local") and t["name"] == r["name"] for t in targets)
        if is_local:
            return (0, 0)
        name_order = {r2["name"]: i + 1 for i, r2 in enumerate(targets)}
        return (1, name_order.get(r["name"], 999))

    results.sort(key=sort_key)
    return results
