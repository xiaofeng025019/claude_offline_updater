import json

import pytest

from claude_offline_updater.history import (
    EVENT_ADD,
    EVENT_FIRST_SEEN,
    EVENT_IP_CHANGE,
    EVENT_PIN,  # NEW
    EVENT_REMOVE,
    EVENT_RENAME,
    EVENT_ROLLBACK,
    EVENT_UNPIN,  # NEW
    EVENT_UPDATE,
    _read_records,
    get_history,
    record_batch,
    record_event,
    record_rollback,
)


@pytest.fixture
def history_file(tmp_path, monkeypatch):
    path = tmp_path / "history.jsonl"
    import claude_offline_updater.history as hist_mod
    monkeypatch.setattr(hist_mod, "HISTORY_PATH", path)
    return path


class TestReadRecords:
    def test_empty_file(self, history_file):
        history_file.touch()
        assert _read_records() == []

    def test_nonexistent_file(self, history_file):
        assert _read_records() == []

    def test_valid_jsonl(self, history_file):
        records = [
            {"machine_name": "s1", "status": "success"},
            {"machine_name": "s2", "status": "failed"},
        ]
        with open(history_file, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
        result = _read_records()
        assert len(result) == 2
        assert result[0]["machine_name"] == "s1"
        assert result[1]["status"] == "failed"

    def test_invalid_lines_skipped(self, history_file):
        with open(history_file, "w") as f:
            f.write('{"machine_name": "s1", "status": "success"}\n')
            f.write("not valid json\n")
            f.write('{"machine_name": "s2", "status": "failed"}\n')
            f.write("\n")
        result = _read_records()
        assert len(result) == 2
        assert result[0]["machine_name"] == "s1"
        assert result[1]["machine_name"] == "s2"

    def test_old_records_default_to_update_type(self, history_file):
        """Records without event_type field should be treated as 'update'"""
        with open(history_file, "w") as f:
            f.write('{"machine_name": "s1", "status": "success"}\n')
        result = _read_records()
        assert result[0]["event_type"] == "update"


class TestRecordBatch:
    def test_writes_multiple_records(self, history_file):
        results = [
            {"name": "s1", "host": "10.0.0.1", "to_version": "2.0.0", "status": "success",
             "machine_id": "aaa111"},
            {"name": "s2", "host": "10.0.0.2", "to_version": "2.0.0", "status": "failed",
             "detail": "timeout", "duration_seconds": 30, "machine_id": "bbb222"},
        ]
        record_batch(results)
        records = _read_records()
        assert len(records) == 2
        assert records[0]["machine_name"] == "s1"
        assert records[0]["machine_id"] == "aaa111"
        assert records[1]["machine_name"] == "s2"
        assert records[1]["detail"] == "timeout"

    def test_record_batch_includes_event_type(self, history_file):
        results = [
            {"name": "s1", "host": "10.0.0.1", "to_version": "2.0.0",
             "status": "success", "from_version": "1.0.0"},
        ]
        record_batch(results)
        records = _read_records()
        assert records[0]["event_type"] == "update"

    def test_record_batch_install_event_type(self, history_file):
        results = [
            {"name": "s1", "host": "10.0.0.1", "to_version": "2.0.0",
             "status": "success", "from_version": "未安装"},
        ]
        record_batch(results)
        records = _read_records()
        assert records[0]["event_type"] == "install"

    def test_record_batch_install_no_from_version(self, history_file):
        results = [
            {"name": "s1", "host": "10.0.0.1", "to_version": "2.0.0",
             "status": "success"},
        ]
        record_batch(results)
        records = _read_records()
        assert records[0]["event_type"] == "install"


class TestGetHistory:
    def _write_records(self, path, count):
        for i in range(count):
            record = {
                "timestamp": f"2025-01-0{i+1}T00:00:00",
                "machine_name": f"server{i % 2}",
                "machine_host": f"10.0.0.{i}",
                "from_version": "1.0.0",
                "to_version": "2.0.0",
                "status": "success",
                "detail": "",
                "duration_seconds": 1.0,
            }
            with open(path, "a") as f:
                f.write(json.dumps(record) + "\n")

    def test_returns_records_in_reverse_order(self, history_file):
        self._write_records(history_file, 5)
        records = get_history()
        assert len(records) == 5
        assert records[0]["machine_host"] == "10.0.0.4"
        assert records[-1]["machine_host"] == "10.0.0.0"

    def test_machine_filter(self, history_file):
        self._write_records(history_file, 4)
        records = get_history(machine="server0")
        assert all(r["machine_name"] == "server0" for r in records)

    def test_limit(self, history_file):
        self._write_records(history_file, 10)
        records = get_history(limit=3)
        assert len(records) == 3

    def test_empty_history(self, history_file):
        assert get_history() == []

    def test_machine_id_filter(self, history_file):
        # Write records with machine_id
        records = [
            {"machine_name": "old_name", "machine_host": "10.0.0.1",
             "machine_id": "abc123", "from_version": "1.0.0", "to_version": "2.0.0",
             "status": "success", "detail": "", "duration_seconds": 1.0,
             "timestamp": "2025-01-01T00:00:00"},
            {"machine_name": "new_name", "machine_host": "10.0.0.99",
             "machine_id": "abc123", "from_version": "2.0.0", "to_version": "3.0.0",
             "status": "success", "detail": "", "duration_seconds": 1.0,
             "timestamp": "2025-01-02T00:00:00"},
            {"machine_name": "other", "machine_host": "10.0.0.2",
             "machine_id": "xyz789", "from_version": "1.0.0", "to_version": "2.0.0",
             "status": "success", "detail": "", "duration_seconds": 1.0,
             "timestamp": "2025-01-03T00:00:00"},
        ]
        with open(history_file, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

        # Filter by machine_id should find both records despite different name/host
        result = get_history(machine_id="abc123")
        assert len(result) == 2
        assert result[0]["machine_name"] == "new_name"
        assert result[1]["machine_name"] == "old_name"

    def test_machine_id_includes_old_records_without_id(self, history_file):
        """machine_id query also includes old records without machine_id matching by name/host"""
        records = [
            {"machine_name": "public_kfj", "machine_host": "10.0.0.1",
             "machine_id": "", "from_version": "1.0.0", "to_version": "2.0.0",
             "status": "success", "detail": "", "duration_seconds": 1.0,
             "timestamp": "2025-01-01T00:00:00"},
            {"machine_name": "public_kfj", "machine_host": "10.0.0.1",
             "machine_id": "abc123", "from_version": "2.0.0", "to_version": "3.0.0",
             "status": "success", "detail": "", "duration_seconds": 1.0,
             "timestamp": "2025-01-02T00:00:00"},
            {"machine_name": "other", "machine_host": "10.0.0.2",
             "machine_id": "xyz789", "from_version": "1.0.0", "to_version": "2.0.0",
             "status": "success", "detail": "", "duration_seconds": 1.0,
             "timestamp": "2025-01-03T00:00:00"},
        ]
        with open(history_file, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

        # Should return both: the record with matching machine_id AND the old one without
        result = get_history(machine_id="abc123", machine="public_kfj", host="10.0.0.1")
        assert len(result) == 2
        assert result[0]["to_version"] == "3.0.0"
        assert result[1]["to_version"] == "2.0.0"

    def test_machine_id_takes_priority_over_name(self, history_file):
        records = [
            {"machine_name": "server1", "machine_host": "10.0.0.1",
             "machine_id": "m1", "from_version": "1.0.0", "to_version": "2.0.0",
             "status": "success", "detail": "", "duration_seconds": 1.0,
             "timestamp": "2025-01-01T00:00:00"},
            {"machine_name": "server1", "machine_host": "10.0.0.2",
             "machine_id": "m2", "from_version": "1.0.0", "to_version": "2.0.0",
             "status": "success", "detail": "", "duration_seconds": 1.0,
             "timestamp": "2025-01-02T00:00:00"},
        ]
        with open(history_file, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

        # machine_id=m2 should only match the second record, ignoring name
        result = get_history(machine_id="m2", machine="server1")
        assert len(result) == 1
        assert result[0]["machine_id"] == "m2"


class TestRecordEvent:
    def test_add_event(self, history_file):
        record_event(EVENT_ADD, machine_name="s1", machine_host="10.0.0.1")
        records = _read_records()
        assert len(records) == 1
        assert records[0]["event_type"] == "add"
        assert records[0]["machine_name"] == "s1"

    def test_remove_event(self, history_file):
        record_event(EVENT_REMOVE, machine_name="s1", machine_host="10.0.0.1",
                     machine_id="abc123")
        records = _read_records()
        assert records[0]["event_type"] == "remove"
        assert records[0]["machine_id"] == "abc123"

    def test_rename_event(self, history_file):
        record_event(EVENT_RENAME, machine_name="new_name", machine_host="10.0.0.1",
                     old_name="old_name")
        records = _read_records()
        assert records[0]["event_type"] == "rename"
        assert records[0]["old_name"] == "old_name"
        assert records[0]["machine_name"] == "new_name"

    def test_ip_change_event(self, history_file):
        record_event(EVENT_IP_CHANGE, machine_name="s1", machine_host="10.0.0.2",
                     old_host="10.0.0.1")
        records = _read_records()
        assert records[0]["event_type"] == "ip_change"
        assert records[0]["old_host"] == "10.0.0.1"

    def test_first_seen_event(self, history_file):
        record_event(EVENT_FIRST_SEEN, machine_name="s1", machine_host="10.0.0.1",
                     machine_id="abc123def456")
        records = _read_records()
        assert records[0]["event_type"] == "first_seen"
        assert records[0]["machine_id"] == "abc123def456"

    def test_rejects_update_event_type(self, history_file):
        with pytest.raises(ValueError, match="record_batch"):
            record_event(EVENT_UPDATE, machine_name="s1", machine_host="10.0.0.1")

    def test_rejects_invalid_event_type(self, history_file):
        with pytest.raises(ValueError, match="Invalid"):
            record_event("bogus", machine_name="s1", machine_host="10.0.0.1")

    def test_timestamp_auto_filled(self, history_file):
        record_event(EVENT_ADD, machine_name="s1", machine_host="10.0.0.1")
        records = _read_records()
        assert records[0]["timestamp"]


class TestEventTypeFilter:
    def test_filter_by_event_type(self, history_file):
        record_event(EVENT_ADD, "s1", "10.0.0.1")
        record_event(EVENT_REMOVE, "s2", "10.0.0.2")
        record_event(EVENT_ADD, "s3", "10.0.0.3")
        result = get_history(event_type="add")
        assert len(result) == 2
        assert all(r["event_type"] == "add" for r in result)

    def test_filter_returns_empty_for_unmatched_type(self, history_file):
        record_event(EVENT_ADD, "s1", "10.0.0.1")
        result = get_history(event_type="rename")
        assert result == []

    def test_no_filter_returns_all_types(self, history_file):
        record_event(EVENT_ADD, "s1", "10.0.0.1")
        record_event(EVENT_REMOVE, "s2", "10.0.0.2")
        result = get_history()
        assert len(result) == 2


class TestRecordRollback:
    def test_records_rollback_event(self, history_file):
        record_rollback("server1", "10.0.0.1", "3.0.0", "2.0.0", "success")
        records = _read_records()
        assert len(records) == 1
        assert records[0]["event_type"] == "rollback"
        assert records[0]["from_version"] == "3.0.0"
        assert records[0]["to_version"] == "2.0.0"
        assert records[0]["status"] == "success"

    def test_rollback_with_detail(self, history_file):
        record_rollback("s1", "10.0.0.1", "3.0.0", "2.0.0", "failed",
                        detail="version not found", duration_seconds=5.0)
        records = _read_records()
        assert records[0]["status"] == "failed"
        assert records[0]["detail"] == "version not found"
        assert records[0]["duration_seconds"] == 5.0

    def test_rollback_with_machine_id(self, history_file):
        record_rollback("s1", "10.0.0.1", "3.0.0", "2.0.0", "success",
                        machine_id="abc123")
        records = _read_records()
        assert records[0]["machine_id"] == "abc123"

    def test_record_event_rejects_rollback_type(self, history_file):
        with pytest.raises(ValueError, match="record_rollback"):
            record_event(EVENT_ROLLBACK, machine_name="s1", machine_host="10.0.0.1")

    def test_filter_by_rollback_type(self, history_file):
        record_rollback("s1", "10.0.0.1", "3.0.0", "2.0.0", "success")
        record_event(EVENT_ADD, "s2", "10.0.0.2")
        result = get_history(event_type="rollback")
        assert len(result) == 1
        assert result[0]["event_type"] == "rollback"


class TestRecordPin:
    def test_event_pin_happy_path(self, history_file):
        record_event(EVENT_PIN, machine_name="s1", machine_host="10.0.0.1",
                     machine_id="m1", version="1.0.45")
        records = _read_records()
        assert len(records) == 1
        assert records[0]["event_type"] == "pin"
        assert records[0]["version"] == "1.0.45"
        assert records[0]["machine_id"] == "m1"

    def test_event_pin_requires_version(self, history_file):
        with pytest.raises(ValueError, match="requires version"):
            record_event(EVENT_PIN, machine_name="s1", machine_host="10.0.0.1")

    def test_event_unpin_requires_version(self, history_file):
        with pytest.raises(ValueError, match="requires version"):
            record_event(EVENT_UNPIN, machine_name="s1", machine_host="10.0.0.1")

    def test_event_unpin_happy_path(self, history_file):
        record_event(EVENT_UNPIN, machine_name="s1", machine_host="10.0.0.1",
                     machine_id="m1", version="1.0.45")
        records = _read_records()
        assert records[0]["event_type"] == "unpin"
        assert records[0]["version"] == "1.0.45"

    def test_event_pin_normalizes_empty_machine_id(self, history_file):
        record_event(EVENT_PIN, machine_name="s1", machine_host="10.0.0.1",
                     machine_id=None, version="1.0.45")
        records = _read_records()
        assert records[0]["machine_id"] == ""  # None normalized to ""

    def test_has_recent_pin_no_record_returns_false(self, history_file):
        from claude_offline_updater.history import has_recent_pin
        assert has_recent_pin("m1", "1.0.45") is False

    def test_has_recent_pin_within_window_returns_true(self, history_file):
        from claude_offline_updater.history import has_recent_pin
        record_event(EVENT_PIN, "s1", "10.0.0.1", machine_id="m1", version="1.0.45")
        assert has_recent_pin("m1", "1.0.45", days=30) is True

    def test_has_recent_pin_outside_window_returns_false(self, history_file):
        from datetime import datetime, timedelta

        from claude_offline_updater.history import has_recent_pin
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
        from claude_offline_updater.history import has_recent_pin
        record_event(EVENT_PIN, "s1", "10.0.0.1", machine_id="", version="1.0.45")
        assert has_recent_pin("", "1.0.45", days=30) is False

    def test_latest_pin_no_record_returns_none(self, history_file):
        from claude_offline_updater.history import latest_pin
        assert latest_pin("m1", "1.0.45") is None

    def test_latest_pin_returns_pin_event(self, history_file):
        from claude_offline_updater.history import latest_pin
        record_event(EVENT_PIN, "s1", "10.0.0.1", machine_id="m1", version="1.0.45")
        result = latest_pin("m1", "1.0.45")
        assert result is not None
        assert result["event_type"] == "pin"

    def test_latest_pin_unpin_after_pin_returns_unpin(self, history_file):
        from claude_offline_updater.history import latest_pin
        record_event(EVENT_PIN, "s1", "10.0.0.1", machine_id="m1", version="1.0.45")
        import time
        time.sleep(0.01)
        record_event(EVENT_UNPIN, "s1", "10.0.0.1", machine_id="m1", version="1.0.45")
        result = latest_pin("m1", "1.0.45")
        assert result["event_type"] == "unpin"

    def test_latest_pin_re_pin_after_unpin_returns_pin(self, history_file):
        from claude_offline_updater.history import latest_pin
        record_event(EVENT_PIN, "s1", "10.0.0.1", machine_id="m1", version="1.0.45")
        import time
        time.sleep(0.01)
        record_event(EVENT_UNPIN, "s1", "10.0.0.1", machine_id="m1", version="1.0.45")
        time.sleep(0.01)
        record_event(EVENT_PIN, "s1", "10.0.0.1", machine_id="m1", version="1.0.45")
        result = latest_pin("m1", "1.0.45")
        assert result["event_type"] == "pin"
