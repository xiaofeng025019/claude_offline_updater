# Version Pin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add lightweight (machine, version) pin records to mark known-good versions. Auto-pinned on rollback success; manually pinned via `claude-offline pin` / `unpin`. 30-day dedup window. No effect on `update` / `rollback` behavior.

**Architecture:** Reuse `history.jsonl` with two new event types (`EVENT_PIN`, `EVENT_UNPIN`) and a `version` field. Two new helpers in `history.py` (`has_recent_pin`, `latest_pin`) drive dedup and unpin-existence checks. `record_event` is extended to accept `version` and validate it for pin/unpin. A new `_auto_pin_on_rollback` helper in `deployer.py` writes the auto-pin on rollback success.

**Tech Stack:** Python 3.10+, pytest, click, existing `history.py` JSONL+fctnl infrastructure.

**Spec:** `docs/superpowers/specs/2026-06-01-version-pin-design.md` (delete this spec file after implementation per user request).

---

## File Structure

| File | Change |
|---|---|
| `claude_offline_updater/history.py` | Add 2 constants; extend `record_event` (accept `version`, validate, normalize `machine_id`); add `has_recent_pin`, `latest_pin`; import `timedelta` |
| `claude_offline_updater/config.py` | Add `Settings.pin_dedup_days: int = 30`; add to `DEFAULTS` and `save()` |
| `claude_offline_updater/deployer.py` | Add `_auto_pin_on_rollback` helper; call from `rollback_local` and `rollback_to_machine` success branches |
| `claude_offline_updater/cli.py` | Add `@cli.command() pin` and `unpin`; add `pin_dedup_days` row to `_edit_settings` and `display.show_config_panels` (handled in display.py) |
| `claude_offline_updater/i18n.py` | Add 7 new keys + 2 new event labels |
| `claude_offline_updater/display.py` | Add `pin` / `unpin` cases to `show_oplog_table`; add `pin_dedup_days` row to settings panel |
| `tests/test_history.py` | Add ~7 new tests for `record_event(EVENT_PIN/EVENT_UNPIN)`, `has_recent_pin`, `latest_pin` |
| `tests/test_deployer.py` | Add ~4 new tests for auto-pin on rollback success/failure/dedup |
| `tests/test_cli.py` (new) | ~5 new tests for `pin` / `unpin` commands |
| `config.yaml.example` | Add `pin_dedup_days` line |

---

## Task 1: Add `EVENT_PIN` / `EVENT_UNPIN` constants and extend `record_event`

**Files:**
- Modify: `claude_offline_updater/history.py:12-22,99-126`

- [ ] **Step 1: Write the failing test for `EVENT_PIN` happy path**

Add to `tests/test_history.py` (at end of file, before the last class — find a good insertion point after `TestRecordRollback`):

```python
class TestRecordPin:
    def test_event_pin_happy_path(self, history_file):
        from claude_offline_updater.history import EVENT_PIN
        record_event(EVENT_PIN, machine_name="s1", machine_host="10.0.0.1",
                     machine_id="m1", version="1.0.45")
        records = _read_records()
        assert len(records) == 1
        assert records[0]["event_type"] == "pin"
        assert records[0]["version"] == "1.0.45"
        assert records[0]["machine_id"] == "m1"
```

Add `EVENT_PIN` to the import list at the top of `tests/test_history.py`:

```python
from claude_offline_updater.history import (
    EVENT_ADD,
    EVENT_FIRST_SEEN,
    EVENT_IP_CHANGE,
    EVENT_PIN,                  # NEW
    EVENT_REMOVE,
    EVENT_RENAME,
    EVENT_ROLLBACK,
    EVENT_UNPIN,                # NEW
    EVENT_UPDATE,
    _read_records,
    get_history,
    record_batch,
    record_event,
    record_rollback,
)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_history.py::TestRecordPin::test_event_pin_happy_path -v`
Expected: FAIL with `ImportError: cannot import name 'EVENT_PIN'`

- [ ] **Step 3: Add constants and extend `record_event`**

Edit `claude_offline_updater/history.py`:

Add to top of constants block (after line 18):

```python
EVENT_PIN = "pin"
EVENT_UNPIN = "unpin"
```

Update `VALID_EVENT_TYPES` (line 21-22):

```python
VALID_EVENT_TYPES = (EVENT_UPDATE, EVENT_INSTALL, EVENT_ROLLBACK, EVENT_ADD,
                     EVENT_REMOVE, EVENT_RENAME, EVENT_IP_CHANGE, EVENT_FIRST_SEEN,
                     EVENT_PIN, EVENT_UNPIN)
```

Replace the entire `record_event` function (lines 100-123):

```python
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_history.py::TestRecordPin::test_event_pin_happy_path -v`
Expected: PASS

- [ ] **Step 5: Add 3 more tests for `EVENT_PIN` / `EVENT_UNPIN` validation**

Add to `TestRecordPin` class:

```python
    def test_event_pin_requires_version(self, history_file):
        from claude_offline_updater.history import EVENT_PIN
        with pytest.raises(ValueError, match="requires version"):
            record_event(EVENT_PIN, machine_name="s1", machine_host="10.0.0.1")

    def test_event_unpin_requires_version(self, history_file):
        from claude_offline_updater.history import EVENT_UNPIN
        with pytest.raises(ValueError, match="requires version"):
            record_event(EVENT_UNPIN, machine_name="s1", machine_host="10.0.0.1")

    def test_event_unpin_happy_path(self, history_file):
        from claude_offline_updater.history import EVENT_UNPIN
        record_event(EVENT_UNPIN, machine_name="s1", machine_host="10.0.0.1",
                     machine_id="m1", version="1.0.45")
        records = _read_records()
        assert records[0]["event_type"] == "unpin"
        assert records[0]["version"] == "1.0.45"

    def test_event_pin_normalizes_empty_machine_id(self, history_file):
        from claude_offline_updater.history import EVENT_PIN
        record_event(EVENT_PIN, machine_name="s1", machine_host="10.0.0.1",
                     machine_id=None, version="1.0.45")
        records = _read_records()
        assert records[0]["machine_id"] == ""  # None normalized to ""
```

- [ ] **Step 6: Run all `TestRecordPin` tests**

Run: `pytest tests/test_history.py::TestRecordPin -v`
Expected: 5 passed

- [ ] **Step 7: Commit**

```bash
git add claude_offline_updater/history.py tests/test_history.py
git commit -m "feat: add EVENT_PIN/EVENT_UNPIN event types and extend record_event"
```

---

## Task 2: Add `has_recent_pin` and `latest_pin` helpers

**Files:**
- Modify: `claude_offline_updater/history.py` (add helpers + import `timedelta`)

- [ ] **Step 1: Write the failing tests for `has_recent_pin`**

Add to `TestRecordPin` class in `tests/test_history.py`:

```python
    def test_has_recent_pin_no_record_returns_false(self, history_file):
        from claude_offline_updater.history import EVENT_PIN, has_recent_pin
        assert has_recent_pin("m1", "1.0.45") is False

    def test_has_recent_pin_within_window_returns_true(self, history_file):
        from claude_offline_updater.history import EVENT_PIN, has_recent_pin
        record_event(EVENT_PIN, "s1", "10.0.0.1", machine_id="m1", version="1.0.45")
        assert has_recent_pin("m1", "1.0.45", days=30) is True

    def test_has_recent_pin_outside_window_returns_false(self, history_file):
        from claude_offline_updater.history import EVENT_PIN, has_recent_pin
        # Write a record with an old timestamp
        from datetime import datetime, timedelta
        old_ts = (datetime.now() - timedelta(days=31)).isoformat()
        import json
        with open(history_file, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "event_type": "pin", "timestamp": old_ts,
                "machine_name": "s1", "machine_host": "10.0.0.1",
                "machine_id": "m1", "version": "1.0.45",
            }) + "\n")
        assert has_recent_pin("m1", "1.0.45", days=30) is False

    def test_has_recent_pin_empty_machine_id_returns_false(self, history_file):
        from claude_offline_updater.history import EVENT_PIN, has_recent_pin
        record_event(EVENT_PIN, "s1", "10.0.0.1", machine_id="", version="1.0.45")
        # No machine_id → can't dedupe, allow write
        assert has_recent_pin("", "1.0.45", days=30) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_history.py::TestRecordPin::test_has_recent_pin_no_record_returns_false -v`
Expected: FAIL with `ImportError: cannot import name 'has_recent_pin'`

- [ ] **Step 3: Implement `has_recent_pin`**

In `claude_offline_updater/history.py`, add `timedelta` to the `datetime` import:

```python
from datetime import datetime, timedelta
```

Add the helper at the end of the file:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_history.py::TestRecordPin -v`
Expected: 9 passed

- [ ] **Step 5: Write failing tests for `latest_pin`**

Add to `TestRecordPin` class:

```python
    def test_latest_pin_no_record_returns_none(self, history_file):
        from claude_offline_updater.history import latest_pin
        assert latest_pin("m1", "1.0.45") is None

    def test_latest_pin_returns_pin_event(self, history_file):
        from claude_offline_updater.history import EVENT_PIN, latest_pin
        record_event(EVENT_PIN, "s1", "10.0.0.1", machine_id="m1", version="1.0.45")
        result = latest_pin("m1", "1.0.45")
        assert result is not None
        assert result["event_type"] == "pin"

    def test_latest_pin_unpin_after_pin_returns_unpin(self, history_file):
        from claude_offline_updater.history import EVENT_PIN, EVENT_UNPIN, latest_pin
        record_event(EVENT_PIN, "s1", "10.0.0.1", machine_id="m1", version="1.0.45")
        # Small delay to ensure timestamp ordering
        import time
        time.sleep(0.01)
        record_event(EVENT_UNPIN, "s1", "10.0.0.1", machine_id="m1", version="1.0.45")
        result = latest_pin("m1", "1.0.45")
        assert result["event_type"] == "unpin"

    def test_latest_pin_re_pin_after_unpin_returns_pin(self, history_file):
        from claude_offline_updater.history import EVENT_PIN, EVENT_UNPIN, latest_pin
        record_event(EVENT_PIN, "s1", "10.0.0.1", machine_id="m1", version="1.0.45")
        import time
        time.sleep(0.01)
        record_event(EVENT_UNPIN, "s1", "10.0.0.1", machine_id="m1", version="1.0.45")
        time.sleep(0.01)
        record_event(EVENT_PIN, "s1", "10.0.0.1", machine_id="m1", version="1.0.45")
        result = latest_pin("m1", "1.0.45")
        assert result["event_type"] == "pin"
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `pytest tests/test_history.py::TestRecordPin::test_latest_pin_no_record_returns_none -v`
Expected: FAIL with `ImportError: cannot import name 'latest_pin'`

- [ ] **Step 7: Implement `latest_pin`**

Add to `claude_offline_updater/history.py` (right after `has_recent_pin`):

```python
def latest_pin(machine_id: str, version: str) -> dict | None:
    """Return the most recent pin/unpin event for (machine_id, version),
    or None. The returned event's type reflects current state."""
    if not machine_id or not version:
        return None
    latest = None
    for r in _read_records():
        if (r.get("event_type") in (EVENT_PIN, EVENT_UNPIN)
                and r.get("machine_id") == machine_id
                and r.get("version") == version):
            if latest is None or r.get("timestamp", "") > latest.get("timestamp", ""):
                latest = r
    return latest
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_history.py::TestRecordPin -v`
Expected: 13 passed

- [ ] **Step 9: Run full test suite to confirm no regressions**

Run: `pytest tests/ -q`
Expected: 160 + 13 = 173 passed

- [ ] **Step 10: Commit**

```bash
git add claude_offline_updater/history.py tests/test_history.py
git commit -m "feat: add has_recent_pin and latest_pin helpers"
```

---

## Task 3: Add `Settings.pin_dedup_days` configuration

**Files:**
- Modify: `claude_offline_updater/config.py:12-28,65-81,165-183`
- Modify: `claude_offline_updater/display.py:231-252` (add to settings panel)

- [ ] **Step 1: Add `pin_dedup_days` to `DEFAULTS`**

In `claude_offline_updater/config.py`, add to `DEFAULTS` (after `"lang": "en"`):

```python
    "pin_dedup_days": 30,
```

- [ ] **Step 2: Add to `Settings` dataclass**

In `claude_offline_updater/config.py`, add to `Settings` dataclass (after `lang: str = "en"`):

```python
    pin_dedup_days: int = 30
```

- [ ] **Step 3: Add to `save()` method**

In `claude_offline_updater/config.py` `save()` method, add to the `settings` dict (after `"lang": ...`):

```python
                "pin_dedup_days": self.settings.pin_dedup_days,
```

- [ ] **Step 4: Add to display panel**

In `claude_offline_updater/display.py`, add to `settings_rows` list (after `("scp_bandwidth_limit", ...)` line, around line 244):

```python
        ("pin_dedup_days", f"{s.pin_dedup_days}d", f"{DEFAULTS.get('pin_dedup_days', '')}d"),
```

- [ ] **Step 5: Add to `_edit_settings` field list**

In `claude_offline_updater/cli.py:457-473`, add to `fields` list (after `("scp_bandwidth_limit", ...)`):

```python
        ("pin_dedup_days", str(s.pin_dedup_days), int, "30"),
```

- [ ] **Step 6: Run tests to verify no regression**

Run: `pytest tests/test_config.py -q`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add claude_offline_updater/config.py claude_offline_updater/display.py claude_offline_updater/cli.py
git commit -m "feat: add pin_dedup_days setting (default 30)"
```

---

## Task 4: Add i18n keys for pin/unpin

**Files:**
- Modify: `claude_offline_updater/i18n.py:152-157,165-180`

- [ ] **Step 1: Add 2 event-label keys**

In `claude_offline_updater/i18n.py`, after `"event_first_seen"` line (line 157):

```python
    "event_pin":             {"zh": "标记可用", "en": "Pin"},
    "event_unpin":           {"zh": "取消标记", "en": "Unpin"},
```

- [ ] **Step 2: Add 7 pin-specific keys**

After the `rollback_*` block (after `"rollback_already"`, around line 176), add:

```python
    "pin_recorded":          {"zh": "已标记为可用版本: {machine} @ {version}",
                              "en": "Pinned: {machine} @ {version}"},
    "unpin_recorded":        {"zh": "已取消标记: {machine} @ {version}",
                              "en": "Unpinned: {machine} @ {version}"},
    "pin_no_such_machine":   {"zh": "机器不存在: {name}",
                              "en": "Machine not found: {name}"},
    "pin_version_missing":   {"zh": "机器 {name} 上未找到版本 {version}",
                              "en": "Version {version} not installed on {name}"},
    "unpin_no_record":       {"zh": "{name} @ {version} 没有 pin 记录",
                              "en": "No pin record for {name} @ {version}"},
    "pin_already_recent":    {"zh": "{machine} @ {version} 已在 {days} 天内标记过，跳过",
                              "en": "{machine} @ {version} already pinned within {days} days, skipping"},
    "pin_force":             {"zh": "强制覆盖 {days} 天去重",
                              "en": "Force pin, ignoring {days}-day dedup"},
```

- [ ] **Step 3: Run tests to verify no regression**

Run: `pytest tests/test_i18n.py -q 2>&1 | tail -3`
Expected: all pass (or skip if no i18n test exists)

- [ ] **Step 4: Commit**

```bash
git add claude_offline_updater/i18n.py
git commit -m "feat: add i18n keys for pin/unpin"
```

---

## Task 5: Extend `show_oplog_table` to render `pin` / `unpin` events

**Files:**
- Modify: `claude_offline_updater/display.py:200-209`

- [ ] **Step 1: Add the new event cases**

In `claude_offline_updater/display.py`, insert after the `first_seen` elif block (after line 204) and before the `else:` (line 206):

```python
        elif etype == "pin":
            event_str = f"[green]📌 {t('event_pin')}[/green]"
            detail_str = r.get("version", "")
            duration_str = "-"

        elif etype == "unpin":
            event_str = f"[dim]📌 {t('event_unpin')}[/dim]"
            detail_str = r.get("version", "")
            duration_str = "-"
```

- [ ] **Step 2: Run tests to verify no regression**

Run: `pytest tests/ -q`
Expected: all pass

- [ ] **Step 3: Commit**

```bash
git add claude_offline_updater/display.py
git commit -m "feat: render pin/unpin events in oplog table"
```

---

## Task 6: Add `_auto_pin_on_rollback` and call from rollback success branches

**Files:**
- Modify: `claude_offline_updater/deployer.py` (add helper, call from `rollback_local` and `rollback_to_machine`)

- [ ] **Step 1: Write the failing test for auto-pin on rollback success**

Add to `tests/test_deployer.py` (find a good location — after existing rollback tests, around the end of file):

```python
class TestAutoPinOnRollback:
    @patch("claude_offline_updater.deployer.record_event")
    def test_rollback_local_success_triggers_auto_pin(
        self, mock_record, sample_local, sample_settings,
    ):
        from claude_offline_updater.history import EVENT_PIN
        with patch("claude_offline_updater.deployer.os.path.islink", return_value=False), \
             patch("claude_offline_updater.deployer.subprocess.run") as mock_run, \
             patch("claude_offline_updater.deployer.cleanup_local_versions"):
            install_proc = MagicMock()
            install_proc.returncode = 0
            version_proc = MagicMock()
            version_proc.returncode = 0
            version_proc.stdout = "1.0.0"  # current
            mock_run.side_effect = [install_proc, version_proc]

            result = {
                "name": "localhost", "host": "127.0.0.1",
                "version": "2.0.0", "is_local": True,
                "machine_id": "m1",
            }
            # rollback_local(current="2.0.0", target="1.0.0")
            from claude_offline_updater.deployer import rollback_local
            out = rollback_local("2.0.0", "1.0.0", sample_local, sample_settings,
                                 machine_id="m1")
            assert out["status"] == "success"
            # Verify EVENT_PIN was recorded
            pin_calls = [c for c in mock_record.call_args_list
                         if c.args and c.args[0] == EVENT_PIN]
            assert len(pin_calls) == 1
            assert pin_calls[0].kwargs["version"] == "1.0.0"
            assert pin_calls[0].kwargs["machine_id"] == "m1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_deployer.py::TestAutoPinOnRollback -v`
Expected: FAIL (auto-pin not yet implemented; mock_record won't be called)

- [ ] **Step 3: Add `_auto_pin_on_rollback` helper**

In `claude_offline_updater/deployer.py`, near the top of the file (after imports, before functions), or just above `rollback_local`. Find a good spot — add it right after `_rollback_symlink` definition (around line 371):

```python
def _auto_pin_on_rollback(result: dict, pin_dedup_days: int = 30):
    """If rollback was a clean success, write an EVENT_PIN record.
    Independent of any string status convention — single check.
    Silent skip on dedup (auto path is non-interactive)."""
    if result.get("status") != "success":
        return
    machine_id = result.get("machine_id", "")
    target_version = result.get("to_version", "")
    if not machine_id or not target_version:
        return
    from .history import has_recent_pin, record_event, EVENT_PIN
    if has_recent_pin(machine_id, target_version, days=pin_dedup_days):
        return
    record_event(
        EVENT_PIN,
        machine_name=result["name"],
        machine_host=result["host"],
        machine_id=machine_id,
        version=target_version,
    )
```

- [ ] **Step 4: Call from `rollback_local` success branch**

In `claude_offline_updater/deployer.py` `rollback_local` (line 564-565), replace the success return:

```python
    success(f"{_prefix(name)}{t('rollback_success')}: {current_version} → {target_version}")
    result = {**base_result, "status": "success",
              "duration_seconds": time.time() - start_time}
    _auto_pin_on_rollback(result, pin_dedup_days=settings.pin_dedup_days)
    return result
```

- [ ] **Step 5: Call from `rollback_to_machine` success branch**

In `claude_offline_updater/deployer.py` `rollback_to_machine` (line 634-636), replace the success return:

```python
        success(f"{_prefix(name)}{t('rollback_success')}: {current_version} → {target_version}")
        result = {**base_result, "status": "success",
                  "duration_seconds": time.time() - start_time}
        _auto_pin_on_rollback(result, pin_dedup_days=settings.pin_dedup_days)
        return result
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_deployer.py::TestAutoPinOnRollback -v`
Expected: PASS

- [ ] **Step 7: Add 2 more tests for dedup and failure paths**

Add to `TestAutoPinOnRollback`:

```python
    @patch("claude_offline_updater.deployer.has_recent_pin", return_value=True)
    @patch("claude_offline_updater.deployer.record_event")
    def test_rollback_success_skips_pin_when_recent_exists(
        self, mock_record, mock_recent, sample_local, sample_settings,
    ):
        with patch("claude_offline_updater.deployer.os.path.islink", return_value=False), \
             patch("claude_offline_updater.deployer.subprocess.run") as mock_run, \
             patch("claude_offline_updater.deployer.cleanup_local_versions"):
            install_proc = MagicMock(returncode=0)
            version_proc = MagicMock(returncode=0, stdout="1.0.0")
            mock_run.side_effect = [install_proc, version_proc]

            from claude_offline_updater.deployer import rollback_local
            out = rollback_local("2.0.0", "1.0.0", sample_local, sample_settings,
                                 machine_id="m1")
            assert out["status"] == "success"
            mock_record.assert_not_called()  # skipped due to recent pin

    def test_rollback_failure_does_not_pin(self, sample_local, sample_settings):
        # current == target → skipped (not success)
        from claude_offline_updater.deployer import rollback_local
        with patch("claude_offline_updater.deployer.record_event") as mock_record:
            out = rollback_local("1.0.0", "1.0.0", sample_local, sample_settings,
                                 machine_id="m1")
            assert out["status"] == "skipped"
            mock_record.assert_not_called()
```

- [ ] **Step 8: Run all new tests**

Run: `pytest tests/test_deployer.py::TestAutoPinOnRollback -v`
Expected: 3 passed

- [ ] **Step 9: Run full suite for regressions**

Run: `pytest tests/ -q`
Expected: 173 + 3 = 176 passed

- [ ] **Step 10: Commit**

```bash
git add claude_offline_updater/deployer.py tests/test_deployer.py
git commit -m "feat: auto-write pin record on rollback success"
```

---

## Task 7: Add `claude-offline pin` CLI command

**Files:**
- Modify: `claude_offline_updater/cli.py` (add command after `rollback` command, around line 940)

- [ ] **Step 1: Write the failing test**

Create new file `tests/test_cli.py`:

```python
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from claude_offline_updater.cli import cli
from claude_offline_updater.config import LocalConfig, Machine, Settings


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def sample_config(tmp_path, monkeypatch):
    """Config with one remote machine named 's1' that has '1.0.45' installed."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text("""\
settings:
  max_versions: 3
local:
  enabled: true
machines:
  - name: s1
    host: 10.0.0.1
    user: root
""")
    monkeypatch.setenv("CLAUDE_OFFLINE_CONFIG", str(config_path))
    return config_path


class TestPinCommand:
    @patch("claude_offline_updater.cli.list_installed_versions_remote",
           return_value=["1.0.45", "1.0.50"])
    @patch("claude_offline_updater.cli.record_event")
    def test_pin_happy_path_writes_event(
        self, mock_record, mock_list, runner, sample_config,
    ):
        result = runner.invoke(cli, ["pin", "--machine", "s1", "--version", "1.0.45"])
        assert result.exit_code == 0
        assert mock_record.called
        args, kwargs = mock_record.call_args
        assert args[0] == "pin"
        assert kwargs["version"] == "1.0.45"

    @patch("claude_offline_updater.cli.list_installed_versions_remote",
           return_value=["1.0.50"])
    @patch("claude_offline_updater.cli.record_event")
    def test_pin_version_not_installed_exits_1(
        self, mock_record, mock_list, runner, sample_config,
    ):
        result = runner.invoke(cli, ["pin", "--machine", "s1", "--version", "1.0.45"])
        assert result.exit_code == 1
        mock_record.assert_not_called()

    @patch("claude_offline_updater.cli.list_installed_versions_remote",
           return_value=["1.0.45"])
    @patch("claude_offline_updater.cli.record_event")
    def test_pin_machine_not_in_config_exits_1(
        self, mock_record, mock_list, runner, sample_config,
    ):
        result = runner.invoke(cli, ["pin", "--machine", "nonexistent", "--version", "1.0.45"])
        assert result.exit_code == 1
        mock_record.assert_not_called()

    @patch("claude_offline_updater.cli.has_recent_pin", return_value=True)
    @patch("claude_offline_updater.cli.list_installed_versions_remote",
           return_value=["1.0.45"])
    @patch("claude_offline_updater.cli.record_event")
    def test_pin_recent_dedup_skips(
        self, mock_record, mock_list, mock_recent, runner, sample_config,
    ):
        result = runner.invoke(cli, ["pin", "--machine", "s1", "--version", "1.0.45"])
        assert result.exit_code == 0
        mock_record.assert_not_called()

    @patch("claude_offline_updater.cli.has_recent_pin", return_value=True)
    @patch("claude_offline_updater.cli.list_installed_versions_remote",
           return_value=["1.0.45"])
    @patch("claude_offline_updater.cli.record_event")
    def test_pin_force_bypasses_dedup(
        self, mock_record, mock_list, mock_recent, runner, sample_config,
    ):
        result = runner.invoke(cli, ["pin", "--machine", "s1", "--version", "1.0.45", "--force"])
        assert result.exit_code == 0
        assert mock_record.called
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::TestPinCommand::test_pin_happy_path_writes_event -v`
Expected: FAIL with `No such command 'pin'` (Click reports unknown command)

- [ ] **Step 3: Add `pin` command to `cli.py`**

In `claude_offline_updater/cli.py`, add after the `rollback` command (after the line `@click.pass_context` for rollback, find the end of that function and add below it):

```python
@cli.command()
@click.option("--machine", required=True, help="Machine name from config")
@click.option("--version", "target_version", required=True, help="Version to pin")
@click.option("--force", is_flag=True, default=False,
              help="Bypass 30-day dedup check")
@click.pass_context
def pin(ctx, machine, target_version, force):
    """Manually mark a (machine, version) pair as a known-good pin."""
    from .history import EVENT_PIN, has_recent_pin, record_event
    from .scanner import list_installed_versions_local, list_installed_versions_remote

    config = ctx.obj["config"]
    m = config.find_machine(machine)
    if not m:
        error(t("pin_no_such_machine", name=machine))
        sys.exit(1)

    # Validate version is installed
    is_local = (machine == "localhost" or m.host == "127.0.0.1")
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py::TestPinCommand -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add claude_offline_updater/cli.py tests/test_cli.py
git commit -m "feat: add claude-offline pin command"
```

---

## Task 8: Add `claude-offline unpin` CLI command

**Files:**
- Modify: `claude_offline_updater/cli.py` (add after `pin` command)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_cli.py`:

```python
class TestUnpinCommand:
    @patch("claude_offline_updater.cli.latest_pin",
           return_value={"event_type": "pin", "version": "1.0.45"})
    @patch("claude_offline_updater.cli.record_event")
    def test_unpin_with_record_writes_event(
        self, mock_record, mock_latest, runner, sample_config,
    ):
        result = runner.invoke(cli, ["unpin", "--machine", "s1", "--version", "1.0.45"])
        assert result.exit_code == 0
        assert mock_record.called
        args, kwargs = mock_record.call_args
        assert args[0] == "unpin"
        assert kwargs["version"] == "1.0.45"

    @patch("claude_offline_updater.cli.latest_pin", return_value=None)
    @patch("claude_offline_updater.cli.record_event")
    def test_unpin_no_record_warns_exit_0(
        self, mock_record, mock_latest, runner, sample_config,
    ):
        result = runner.invoke(cli, ["unpin", "--machine", "s1", "--version", "1.0.45"])
        assert result.exit_code == 0
        mock_record.assert_not_called()

    @patch("claude_offline_updater.cli.record_event")
    def test_unpin_machine_not_in_config_exits_1(
        self, mock_record, runner, sample_config,
    ):
        result = runner.invoke(cli, ["unpin", "--machine", "nonexistent", "--version", "1.0.45"])
        assert result.exit_code == 1
        mock_record.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::TestUnpinCommand::test_unpin_with_record_writes_event -v`
Expected: FAIL with `No such command 'unpin'`

- [ ] **Step 3: Add `unpin` command to `cli.py`**

In `claude_offline_updater/cli.py`, add right after the `pin` command:

```python
@cli.command()
@click.option("--machine", required=True, help="Machine name from config")
@click.option("--version", "target_version", required=True, help="Version to unpin")
@click.pass_context
def unpin(ctx, machine, target_version):
    """Remove the most-recent pin record for a (machine, version) pair."""
    from .history import EVENT_UNPIN, latest_pin, record_event

    config = ctx.obj["config"]
    m = config.find_machine(machine)
    if not m:
        error(t("pin_no_such_machine", name=machine))
        sys.exit(1)

    machine_id = m.machine_id or ""
    if latest_pin(machine_id, target_version) is None:
        warn(t("unpin_no_record", name=machine, version=target_version))
        return

    record_event(
        EVENT_UNPIN,
        machine_name=m.name,
        machine_host=m.host,
        machine_id=machine_id,
        version=target_version,
    )
    success(t("unpin_recorded", machine=machine, version=target_version))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py::TestUnpinCommand -v`
Expected: 3 passed

- [ ] **Step 5: Run full suite**

Run: `pytest tests/ -q`
Expected: 176 + 8 = 184 passed

- [ ] **Step 6: Commit**

```bash
git add claude_offline_updater/cli.py tests/test_cli.py
git commit -m "feat: add claude-offline unpin command"
```

---

## Task 9: Update `config.yaml.example` and final verification

**Files:**
- Modify: `config.yaml.example` (add `pin_dedup_days` documentation)

- [ ] **Step 1: Add `pin_dedup_days` to example config**

In `config.yaml.example`, add a documented line. Find a good spot (after `max_retries` or similar numeric setting). Add:

```yaml
  pin_dedup_days: 30                # Auto-pin dedup window (days); 0 = no dedup
```

- [ ] **Step 2: Run full test suite**

Run: `pytest tests/ -q`
Expected: 184 passed

- [ ] **Step 3: Run linter**

Run: `python -m ruff check claude_offline_updater/ scripts/`
Expected: All checks passed

- [ ] **Step 4: Test the CLI manually**

Run: `claude-offline pin --help`
Expected: shows the new command with --machine, --version, --force options

Run: `claude-offline unpin --help`
Expected: shows the new command with --machine, --version options

- [ ] **Step 5: Reinstall the package**

Run: `pip install -e . -q`

- [ ] **Step 6: Commit**

```bash
git add config.yaml.example
git commit -m "docs: document pin_dedup_days in config example"
```

---

## Task 10: Delete spec file and final cleanup

- [ ] **Step 1: Delete the design spec file (per user request)**

```bash
rm -rf docs/superpowers/specs/2026-06-01-version-pin-design.md
rm -rf docs/superpowers/specs/  # if now empty
```

(Only delete the spec; keep `docs/superpowers/plans/` for the plan record.)

- [ ] **Step 2: Push to main and verify auto-bump**

```bash
git push
```

Then `git pull --tags` and verify version bumped to 1.2.0.

- [ ] **Step 3: Reinstall and smoke-test**

```bash
pip install -e . -q
claude-offline --version
```

Expected: 1.2.0 (or whatever auto-bump produced)

---

## Self-Review

1. **Spec coverage** — every spec section has a task:
   - §1 Data model → Task 1
   - §2 record_event extension → Task 1
   - §3 Auto-pin on rollback → Task 6
   - §4 Manual pin/unpin → Tasks 7, 8
   - §5 latest_pin → Task 2
   - §6 30-day dedup → Tasks 2, 3, 7
   - §7 Error handling → covered across tasks (table maps to specific test cases)
   - §8 i18n keys → Task 4
   - §9 show_oplog_table → Task 5
   - §10 Compatibility → no task needed (default behavior preserved); verified by full test suite in each task

2. **Placeholder scan** — no TBD/TODO/fill-in markers; every code block complete.

3. **Type consistency** —
   - `record_event` signature in Task 1 matches all call sites in Tasks 6, 7, 8 (kw-only `version` param).
   - `has_recent_pin(machine_id, version, days=30)` signature consistent across Task 2 and Tasks 6, 7.
   - `latest_pin(machine_id, version)` signature consistent across Task 2 and Task 8.
   - `_auto_pin_on_rollback(result, pin_dedup_days=30)` signature consistent in Task 6.
   - `EVENT_PIN` / `EVENT_UNPIN` strings consistent across all tasks.
