"""Parallel machine version scanning (local + remote)"""

import contextlib
import logging
import os
import re
import shlex
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import paramiko

from .config import LocalConfig, Machine, Settings
from .i18n import t

# Suppress paramiko's noisy transport-level logging (connection failures
# print stack traces to stderr via logging). Only show CRITICAL.
logging.getLogger("paramiko").setLevel(logging.CRITICAL)


def scan_local(local: LocalConfig) -> dict:
    """Get local machine's Claude Code version"""
    claude_bin = os.path.expanduser(local.claude_bin)
    versions_dir = os.path.expanduser(local.versions_dir)
    version = _get_local_version(claude_bin, versions_dir)

    return {
        "name": "localhost",
        "host": "127.0.0.1",
        "port": "-",
        "user": os.environ.get("USER", "unknown"),
        "version": version,
        "tags": ["local"],
        "is_local": True,
        "machine_id": _read_local_machine_id(),
    }


def _get_local_version(configured_bin: str, versions_dir: str) -> str:
    """Detect local Claude Code version.

    Prefer the configured managed binary path, then fall back to `claude` on
    PATH. If the entrypoint is missing but managed version files exist, use the
    newest executable version so scans don't report "Not installed" after a
    stale/missing symlink.
    """
    candidates = [(configured_bin, True)]
    path_bin = shutil.which("claude")
    if path_bin and path_bin != configured_bin:
        candidates.append((path_bin, False))

    for candidate, require_exists in candidates:
        version = _get_version_from_binary(candidate, require_exists=require_exists)
        if version:
            return version

    latest_managed = _get_latest_managed_version(versions_dir)
    if latest_managed:
        return latest_managed
    return t("status_not_installed")


def _get_version_from_binary(binary: str, require_exists: bool = True) -> str:
    if require_exists and not (os.path.islink(binary) or os.path.isfile(binary)):
        return ""
    try:
        result = subprocess.run(
            [binary, "--version"],
            capture_output=True, text=True, timeout=10,
        )
        match = re.search(r'(\d+\.\d+\.\d+)', result.stdout)
        if match:
            return match.group(1)
    except Exception:
        pass
    return ""


def _get_latest_managed_version(versions_dir: str) -> str:
    if not os.path.isdir(versions_dir):
        return ""
    versions = []
    for name in os.listdir(versions_dir):
        path = os.path.join(versions_dir, name)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            versions.append(name)
    if not versions:
        return ""
    versions.sort(key=_version_key, reverse=True)
    return versions[0]


def scan_machine(machine: Machine, settings: Settings) -> dict:
    """Get a single remote machine's Claude Code version"""
    version, machine_id = _get_remote_info(machine, settings)
    return {
        "name": machine.name,
        "host": machine.host,
        "port": machine.port,
        "user": machine.user,
        "version": version,
        "tags": machine.tags,
        "is_local": False,
        "machine_id": machine_id or machine.machine_id,
    }


def scan_all(machines: list[Machine], settings: Settings,
             local: LocalConfig | None = None) -> list[dict]:
    """Scan all machines in parallel (including local)"""
    results = []

    # Scan local first
    if local and local.enabled:
        results.append(scan_local(local))

    # Scan remotes in parallel
    if machines:
        with ThreadPoolExecutor(max_workers=min(settings.max_workers, len(machines))) as pool:
            futures = {
                pool.submit(scan_machine, m, settings): m
                for m in machines
            }
            for future in as_completed(futures):
                machine = futures[future]
                try:
                    results.append(future.result())
                except Exception:
                    results.append({
                        "name": machine.name,
                        "host": machine.host,
                        "port": machine.port,
                        "user": machine.user,
                        "version": t("status_conn_failed"),
                        "tags": machine.tags,
                        "is_local": False,
                        "machine_id": machine.machine_id,
                    })

    # Sort: local first, remote in original order
    def sort_key(r):
        if r.get("is_local"):
            return (0, 0)
        name_order = {m.name: i + 1 for i, m in enumerate(machines)}
        return (1, name_order.get(r["name"], 999))

    results.sort(key=sort_key)
    return results


def _get_remote_info(machine: Machine, settings: Settings) -> tuple[str, str]:
    """Get remote Claude version and machine-id via SSH"""
    client = None
    try:
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
        client.connect(
            machine.host,
            port=machine.port,
            username=machine.user,
            timeout=settings.connect_timeout,
        )

        # Get version
        version = t("status_not_installed")
        stdin, stdout, stderr = client.exec_command(
            f"{shlex.quote(settings.remote_claude_bin)} --version 2>/dev/null",
            timeout=10,
        )
        output = stdout.read().decode().strip()
        if output:
            match = re.search(r'(\d+\.\d+\.\d+)', output)
            if match:
                version = match.group(1)

        # Get machine-id
        machine_id = _read_remote_machine_id(client)

        return version, machine_id

    except Exception:
        return t("status_conn_failed"), ""
    finally:
        if client:
            with contextlib.suppress(Exception):
                client.close()


def _read_remote_machine_id(client: paramiko.SSHClient) -> str:
    """Read /etc/machine-id from remote machine"""
    try:
        stdin, stdout, stderr = client.exec_command(
            "cat /etc/machine-id 2>/dev/null", timeout=5,
        )
        mid = stdout.read().decode().strip()
        # Validate: should be 32 hex chars
        if len(mid) == 32 and all(c in "0123456789abcdef" for c in mid):
            return mid
    except Exception:
        pass
    return ""


def _read_local_machine_id() -> str:
    """Read /etc/machine-id from local machine"""
    try:
        mid = Path("/etc/machine-id").read_text().strip()
        if len(mid) == 32 and all(c in "0123456789abcdef" for c in mid):
            return mid
    except Exception:
        pass
    return ""


def list_installed_versions_local(local: LocalConfig) -> list[str]:
    """List installed Claude versions on local machine, newest first"""
    versions_dir = os.path.expanduser(local.versions_dir)
    if not os.path.isdir(versions_dir):
        return []
    versions = []
    for name in os.listdir(versions_dir):
        path = os.path.join(versions_dir, name)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            versions.append(name)
    versions.sort(key=_version_key, reverse=True)
    return versions


def list_installed_versions_remote(machine: Machine, settings: Settings) -> list[str]:
    """List installed Claude versions on remote machine, newest first"""
    client = None
    try:
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
        client.connect(
            machine.host, port=machine.port, username=machine.user,
            timeout=settings.connect_timeout,
        )
        vdir = shlex.quote(settings.remote_versions_dir)
        stdin, stdout, stderr = client.exec_command(
            f"ls -1 {vdir}/ 2>/dev/null", timeout=10,
        )
        output = stdout.read().decode().strip()
        if not output:
            return []
        versions = [v for v in output.splitlines() if v.strip()]
        versions.sort(key=_version_key, reverse=True)
        return versions
    except Exception:
        return []
    finally:
        if client:
            with contextlib.suppress(Exception):
                client.close()


def _version_key(v: str) -> tuple:
    """Parse version string into sortable tuple"""
    parts = v.split(".")
    result = []
    for p in parts:
        try:
            result.append(int(p))
        except ValueError:
            result.append(0)
    return tuple(result)
