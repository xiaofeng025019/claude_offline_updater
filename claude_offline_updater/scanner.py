"""Parallel machine version scanning (local + remote)"""

import contextlib
import logging
import os
import re
import shlex
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
    version = t("status_not_installed")

    if os.path.islink(claude_bin) or os.path.isfile(claude_bin):
        try:
            result = subprocess.run(
                [claude_bin, "--version"],
                capture_output=True, text=True, timeout=10,
            )
            match = re.search(r'(\d+\.\d+\.\d+)', result.stdout)
            if match:
                version = match.group(1)
        except Exception:
            pass

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
