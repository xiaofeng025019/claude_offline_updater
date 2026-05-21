import json

import pytest

from claude_offline_updater.history import (
    _read_records,
    get_history,
    record_batch,
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


class TestRecordBatch:
    def test_writes_multiple_records(self, history_file):
        results = [
            {"name": "s1", "host": "10.0.0.1", "to_version": "2.0.0", "status": "success"},
            {"name": "s2", "host": "10.0.0.2", "to_version": "2.0.0", "status": "failed",
             "detail": "timeout", "duration_seconds": 30},
        ]
        record_batch(results)
        records = _read_records()
        assert len(records) == 2
        assert records[0]["machine_name"] == "s1"
        assert records[1]["machine_name"] == "s2"
        assert records[1]["detail"] == "timeout"


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
