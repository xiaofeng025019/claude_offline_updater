"""JSONL file update history tracking (replaces SQLite to avoid environment dependency issues)"""

import fcntl
import json
import tempfile
from datetime import datetime
from pathlib import Path

HISTORY_PATH = Path.home() / ".local" / "share" / "claude-update" / "history.jsonl"


def _read_records() -> list[dict]:
    """Read all history records"""
    if not HISTORY_PATH.exists():
        return []
    records = []
    with open(HISTORY_PATH, encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_SH)
        try:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    return records


def _append_record(record: dict):
    """Append a single record"""
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_PATH, "a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def record_batch(results: list[dict]):
    """Batch record update results"""
    now = datetime.now().isoformat()
    for r in results:
        _append_record({
            "timestamp": now,
            "machine_name": r["name"],
            "machine_host": r["host"],
            "machine_id": r.get("machine_id", ""),
            "from_version": r.get("from_version", ""),
            "to_version": r["to_version"],
            "status": r["status"],
            "detail": r.get("detail", ""),
            "duration_seconds": r.get("duration_seconds", 0),
        })


def get_history(machine: str | None = None, host: str | None = None,
                machine_id: str | None = None, limit: int = 50) -> list[dict]:
    """Query update history, preferring machine_id for stable identity"""
    records = _read_records()

    if machine_id:
        # machine_id takes priority — matches across renames and IP changes
        # Also include old records without machine_id that match by name/host (defensive fallback)
        records = [r for r in records
                   if r.get("machine_id") == machine_id
                   or (not r.get("machine_id")
                       and ((machine and r.get("machine_name") == machine)
                            or (host and r.get("machine_host") == host)))]
    elif machine or host:
        records = [r for r in records
                   if (machine and r.get("machine_name") == machine)
                   or (host and r.get("machine_host") == host)]

    # Sort by time descending, take latest limit records
    records.reverse()
    return records[:limit]


def backfill_machine_id(machine_name: str, machine_host: str, machine_id: str):
    """Fill machine_id into old history records that match by name or host but lack it"""
    if not machine_id:
        return

    records = _read_records()
    changed = False
    for r in records:
        if r.get("machine_id"):
            continue
        if r.get("machine_name") == machine_name or r.get("machine_host") == machine_host:
            r["machine_id"] = machine_id
            changed = True

    if not changed:
        return

    # Rewrite the file with updated records
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".jsonl",
        dir=HISTORY_PATH.parent, delete=False,
    ) as tmp:
        fcntl.flock(tmp, fcntl.LOCK_EX)
        try:
            for r in records:
                tmp.write(json.dumps(r, ensure_ascii=False) + "\n")
        finally:
            fcntl.flock(tmp, fcntl.LOCK_UN)
        tmp_path = tmp.name
    import os
    os.replace(tmp_path, HISTORY_PATH)
