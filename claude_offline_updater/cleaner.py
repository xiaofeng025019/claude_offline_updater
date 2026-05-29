"""Remote/local old version cleanup"""

import os
import shlex

import paramiko

from .config import LocalConfig, Settings
from .display import _prefix, info, success
from .i18n import t


def cleanup_old_versions(client: paramiko.SSHClient, settings: Settings,
                         label: str = ""):
    """Clean remote old versions (keep latest N valid versions)"""
    prefix = _prefix(label)
    info(f"{prefix}{t('cleaning_remote')}")

    max_ver = int(settings.max_versions)
    quoted_dir = shlex.quote(settings.remote_versions_dir)
    cleanup_script = f"""
cd {quoted_dir} 2>/dev/null || exit 0

# Remove invalid files (0 bytes or non-executable)
for f in *; do
    [ -f "$f" ] || continue
    if [ ! -s "$f" ] || [ ! -x "$f" ]; then
        rm -f "$f"
    fi
done

# Sort by mtime, keep latest N
versions=($(ls -t 2>/dev/null))
total=${{#versions[@]}}
if [ "$total" -gt {max_ver} ]; then
    for v in "${{versions[@]:{max_ver}}}"; do
        rm -f "$v"
    done
fi

ls -lh 2>/dev/null | awk 'NR>1 {{print "  " $NF " (" $5 ")"}}'
"""

    stdin, stdout, stderr = client.exec_command(cleanup_script, timeout=15)
    output = stdout.read().decode().strip()
    if output:
        info(f"{prefix}{t('kept_versions')}:\n{output}")

    success(f"{prefix}{t('remote_clean_done')}")


def cleanup_local_versions(local: LocalConfig, max_versions: int,
                           label: str = "localhost"):
    """Clean local old versions (keep latest N valid versions)"""
    max_versions = int(max_versions)
    prefix = _prefix(label)
    info(f"{prefix}{t('cleaning_local')}")
    versions_dir = os.path.expanduser(local.versions_dir)

    if not os.path.isdir(versions_dir):
        return

    entries = []
    for name in os.listdir(versions_dir):
        path = os.path.join(versions_dir, name)
        if not os.path.isfile(path):
            continue

        if os.path.getsize(path) == 0:
            os.remove(path)
            info(f"{prefix}  {t('clean_invalid')}: {name}")
            continue
        if not os.access(path, os.X_OK):
            os.remove(path)
            info(f"{prefix}  {t('clean_invalid')}: {name}")
            continue

        entries.append((os.path.getmtime(path), name, path))

    entries.sort(reverse=True)

    if len(entries) > max_versions:
        for _, name, path in entries[max_versions:]:
            os.remove(path)
            info(f"{prefix}  {t('clean_old')}: {name}")

    remaining = [e[1] for e in entries[:max_versions]]
    if remaining:
        info(f"{prefix}{t('kept_versions')}: {', '.join(remaining)}")

    success(f"{prefix}{t('local_clean_done')}")
