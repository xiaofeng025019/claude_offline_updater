"""JSONL operation log tracking (generalized from update history)"""

import fcntl
import json
import tempfile
from datetime import datetime
from pathlib import Path

HISTORY_PATH = Path.home() / ".local" / "share" / "claude-update" / "history.jsonl"

EVENT_UPDATE = "update"
EVENT_ADD = "add"
EVENT_REMOVE = "remove"
EVENT_RENAME = "rename"
EVENT_IP_CHANGE = "ip_change"
EVENT_FIRST_SEEN = "first_seen"

VALID_EVENT_TYPES = (EVENT_UPDATE, EVENT_ADD, EVENT_REMOVE,
                     EVENT_RENAME, EVENT_IP_CHANGE, EVENT_FIRST_SEEN)


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
                        record = json.loads(line)
                        record.setdefault("event_type", EVENT_UPDATE)
                        records.append(record)
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
            "event_type": EVENT_UPDATE,
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


def record_event(event_type: str, machine_name: str, machine_host: str,
                 machine_id: str = "", **kwargs):
    """Record a non-update operation event"""
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(f"Invalid event_type: {event_type}")
    if event_type == EVENT_UPDATE:
        raise ValueError("Use record_batch() for update events")

    record = {
        "event_type": event_type,
        "timestamp": datetime.now().isoformat(),
        "machine_name": machine_name,
        "machine_host": machine_host,
        "machine_id": machine_id,
    }
    if event_type == EVENT_RENAME:
        record["old_name"] = kwargs.get("old_name", "")
    elif event_type == EVENT_IP_CHANGE:
        record["old_host"] = kwargs.get("old_host", "")

    _append_record(record)


def get_history(machine: str | None = None, host: str | None = None,
                machine_id: str | None = None, event_type: str | None = None,
                limit: int = 50) -> list[dict]:
    """Query operation log, preferring machine_id for stable identity"""
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

    if event_type:
        records = [r for r in records if r.get("event_type") == event_type]

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
