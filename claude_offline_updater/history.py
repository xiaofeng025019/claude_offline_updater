"""JSONL file update history tracking (replaces SQLite to avoid environment dependency issues)"""

import fcntl
import json
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
            "from_version": r.get("from_version", ""),
            "to_version": r["to_version"],
            "status": r["status"],
            "detail": r.get("detail", ""),
            "duration_seconds": r.get("duration_seconds", 0),
        })


def get_history(machine: str | None = None, host: str | None = None,
                limit: int = 50) -> list[dict]:
    """Query update history, matching by name and/or host to handle renames"""
    records = _read_records()

    if machine or host:
        records = [r for r in records
                   if (machine and r.get("machine_name") == machine)
                   or (host and r.get("machine_host") == host)]

    # Sort by time descending, take latest limit records
    records.reverse()
    return records[:limit]
