"""JSONL operation log tracking (generalized from update history)"""

import fcntl
import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

HISTORY_PATH = Path.home() / ".local" / "share" / "claude-update" / "history.jsonl"

EVENT_UPDATE = "update"
EVENT_INSTALL = "install"
EVENT_ROLLBACK = "rollback"
EVENT_ADD = "add"
EVENT_REMOVE = "remove"
EVENT_RENAME = "rename"
EVENT_IP_CHANGE = "ip_change"
EVENT_FIRST_SEEN = "first_seen"
EVENT_PIN = "pin"
EVENT_UNPIN = "unpin"

VALID_EVENT_TYPES = (EVENT_UPDATE, EVENT_INSTALL, EVENT_ROLLBACK, EVENT_ADD,
                     EVENT_REMOVE, EVENT_RENAME, EVENT_IP_CHANGE, EVENT_FIRST_SEEN,
                     EVENT_PIN, EVENT_UNPIN)


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
                        # Normalize None machine_id to empty string
                        if record.get("machine_id") is None:
                            record["machine_id"] = ""
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
        from_ver = r.get("from_version", "")
        is_install = not from_ver or from_ver in ("未安装", "Not installed")
        _append_record({
            "event_type": EVENT_INSTALL if is_install else EVENT_UPDATE,
            "timestamp": now,
            "machine_name": r["name"],
            "machine_host": r["host"],
            "machine_id": r.get("machine_id") or "",
            "from_version": from_ver,
            "to_version": r["to_version"],
            "status": r["status"],
            "detail": r.get("detail", ""),
            "duration_seconds": r.get("duration_seconds", 0),
        })


def record_rollback(machine_name: str, machine_host: str,
                    from_version: str, to_version: str, status: str,
                    machine_id: str = "", detail: str = "",
                    duration_seconds: float = 0):
    """Record a rollback event"""
    _append_record({
        "event_type": EVENT_ROLLBACK,
        "timestamp": datetime.now().isoformat(),
        "machine_name": machine_name,
        "machine_host": machine_host,
        "machine_id": machine_id or "",
        "from_version": from_version,
        "to_version": to_version,
        "status": status,
        "detail": detail,
        "duration_seconds": duration_seconds,
    })


def record_event(event_type: str, machine_name: str, machine_host: str,
                 machine_id: str = "", *, old_name: str = "",
                 old_host: str = "", version: str = ""):
    """Record a non-update operation event"""
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(f"Invalid event_type: {event_type}")
    if event_type == EVENT_UPDATE:
        raise ValueError("Use record_batch() for update events")
    if event_type == EVENT_INSTALL:
        raise ValueError("Use record_batch() for install events")
    if event_type == EVENT_ROLLBACK:
        raise ValueError("Use record_rollback() for rollback events")
    if event_type in (EVENT_PIN, EVENT_UNPIN) and not version:
        raise ValueError(f"record_event({event_type}, ...) requires version=")
    if event_type == EVENT_RENAME and not old_name:
        raise ValueError("record_event(EVENT_RENAME, ...) requires old_name=")
    if event_type == EVENT_IP_CHANGE and not old_host:
        raise ValueError("record_event(EVENT_IP_CHANGE, ...) requires old_host=")

    record = {
        "event_type": event_type,
        "timestamp": datetime.now().isoformat(),
        "machine_name": machine_name,
        "machine_host": machine_host,
        "machine_id": machine_id or "",
    }
    if event_type == EVENT_RENAME:
        record["old_name"] = old_name
    elif event_type == EVENT_IP_CHANGE:
        record["old_host"] = old_host
    elif event_type in (EVENT_PIN, EVENT_UNPIN):
        record["version"] = version

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
    # Lock HISTORY_PATH (not the temp file) so concurrent _append_record blocks
    with open(HISTORY_PATH, "a", encoding="utf-8") as lockf:
        fcntl.flock(lockf, fcntl.LOCK_EX)
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", suffix=".jsonl",
                dir=HISTORY_PATH.parent, delete=False,
            ) as tmp:
                for r in records:
                    tmp.write(json.dumps(r, ensure_ascii=False) + "\n")
                tmp_path = tmp.name
            os.replace(tmp_path, HISTORY_PATH)
        finally:
            fcntl.flock(lockf, fcntl.LOCK_UN)


def backfill_events():
    """Detect and insert missing rename/first_seen events, then rewrite file in order"""
    records = _read_records()
    if not records:
        return

    # Build set of existing non-update events to avoid duplicates
    # Key on (event_type, timestamp, machine_id) to avoid false-positive suppression
    # when multiple machines share a timestamp
    existing_events = set()
    for r in records:
        if r.get("event_type") != EVENT_UPDATE:
            etype = r["event_type"]
            ts = r["timestamp"]
            mid = r.get("machine_id") or ""
            existing_events.add((etype, ts, mid))

    new_events = []

    # Detect renames: same host, different name, name changes in chronological order
    by_host: dict[str, list[dict]] = {}
    for r in records:
        h = r["machine_host"]
        if h not in by_host:
            by_host[h] = []
        by_host[h].append(r)

    for host, recs in by_host.items():
        recs_sorted = sorted(recs, key=lambda x: x["timestamp"])
        seen_names: dict[str, str] = {}  # name -> first timestamp
        prev_name = None
        for r in recs_sorted:
            name = r["machine_name"]
            if prev_name is not None and name != prev_name and name not in seen_names:
                # Name changed at this point
                event_key = (EVENT_RENAME, r["timestamp"], r.get("machine_id") or "")
                if event_key not in existing_events:
                    new_events.append({
                        "event_type": EVENT_RENAME,
                        "timestamp": r["timestamp"],
                        "machine_name": name,
                        "machine_host": host,
                        "machine_id": r.get("machine_id") or "",
                        "old_name": prev_name,
                    })
            seen_names.setdefault(name, r["timestamp"])
            prev_name = name

    # Detect first_seen: first record with a non-empty machine_id per machine_id
    seen_mids: set[str] = set()
    records_by_time = sorted(records, key=lambda x: x["timestamp"])
    for r in records_by_time:
        mid = r.get("machine_id", "")
        if mid and mid not in seen_mids:
            seen_mids.add(mid)
            # Only if there isn't already a first_seen event for this mid
            already_has = any(
                e.get("event_type") == EVENT_FIRST_SEEN and e.get("machine_id") == mid
                for e in records if e.get("event_type") != EVENT_UPDATE
            )
            if not already_has:
                new_events.append({
                    "event_type": EVENT_FIRST_SEEN,
                    "timestamp": r["timestamp"],
                    "machine_name": r["machine_name"],
                    "machine_host": r["machine_host"],
                    "machine_id": mid,
                })

    # Merge old + new records, ensure event_type on all, sort by time, rewrite file
    all_records = records + new_events
    for r in all_records:
        r.setdefault("event_type", EVENT_UPDATE)
        # Reclassify old "update" records with from_version="未安装"/"Not installed" as install
        if r["event_type"] == EVENT_UPDATE:
            from_ver = r.get("from_version", "")
            if not from_ver or from_ver in ("未安装", "Not installed"):
                r["event_type"] = EVENT_INSTALL
    all_records.sort(key=lambda x: x["timestamp"])

    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Lock HISTORY_PATH (not the temp file) so concurrent _append_record blocks
    with open(HISTORY_PATH, "a", encoding="utf-8") as lockf:
        fcntl.flock(lockf, fcntl.LOCK_EX)
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", suffix=".jsonl",
                dir=HISTORY_PATH.parent, delete=False,
            ) as tmp:
                for r in all_records:
                    tmp.write(json.dumps(r, ensure_ascii=False) + "\n")
                tmp_path = tmp.name
            os.replace(tmp_path, HISTORY_PATH)
        finally:
            fcntl.flock(lockf, fcntl.LOCK_UN)


def has_recent_pin(machine_id: str, version: str, days: int = 30) -> bool:
    """Return True if a pin event for (machine_id, version) exists within `days`."""
    if not machine_id or not version:
        return False
    cutoff = datetime.now() - timedelta(days=days)
    for r in _read_records():
        if (r.get("event_type") == EVENT_PIN
                and r.get("machine_id") == machine_id
                and r.get("version") == version):
            try:
                ts = datetime.fromisoformat(r["timestamp"])
            except (ValueError, TypeError):
                continue
            if ts >= cutoff:
                return True
    return False


def latest_pin(machine_id: str, version: str) -> dict | None:
    """Return the most recent pin/unpin event for (machine_id, version),
    or None. The returned event's type reflects current state."""
    if not machine_id or not version:
        return None
    latest = None
    for r in _read_records():
        if (r.get("event_type") in (EVENT_PIN, EVENT_UNPIN)
                and r.get("machine_id") == machine_id
                and r.get("version") == version
                and (latest is None
                     or r.get("timestamp", "") > latest.get("timestamp", ""))):
            latest = r
    return latest
