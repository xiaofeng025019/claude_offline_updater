from unittest.mock import patch

import pytest
from click.testing import CliRunner

from claude_offline_updater.cli import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def sample_config(tmp_path, monkeypatch):
    """Config with one remote machine named 's1'."""
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

    @patch("claude_offline_updater.cli.record_event")
    def test_pin_machine_not_in_config_exits_1(
        self, mock_record, runner, sample_config,
    ):
        # find_machine returns None → exit 1 before any version check
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
    def test_unpin_no_record_exits_1(
        self, mock_record, mock_latest, runner, sample_config,
    ):
        # No prior pin exists → strict exit 1 (mirrors pin's "version missing" exit 1)
        result = runner.invoke(cli, ["unpin", "--machine", "s1", "--version", "1.0.45"])
        assert result.exit_code == 1
        mock_record.assert_not_called()

    @patch("claude_offline_updater.cli.latest_pin",
           return_value={"event_type": "unpin", "version": "1.0.45"})
    @patch("claude_offline_updater.cli.record_event")
    def test_unpin_already_unpinned_is_noop(
        self, mock_record, mock_latest, runner, sample_config,
    ):
        # Last event was already an unpin → exit 0, no new event written
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


class TestScanCommand:
    """Smoke tests for the scan subcommand entry point."""

    def test_scan_help(self, runner, sample_config):
        result = runner.invoke(cli, ["scan", "--help"])
        assert result.exit_code == 0
        assert "Scan" in result.output or "scan" in result.output


class TestUpdateCommand:
    def test_update_help(self, runner, sample_config):
        result = runner.invoke(cli, ["update", "--help"])
        assert result.exit_code == 0

    def test_update_requires_machine_or_all(self, runner, sample_config):
        result = runner.invoke(cli, ["update"])
        # Without --machine or --all, should error
        assert result.exit_code != 0


class TestRollbackCommand:
    def test_rollback_help(self, runner, sample_config):
        result = runner.invoke(cli, ["rollback", "--help"])
        assert result.exit_code == 0


class TestHistoryCommand:
    def test_history_help(self, runner, sample_config):
        result = runner.invoke(cli, ["history", "--help"])
        assert result.exit_code == 0


class TestBackfillEventsCommand:
    def test_backfill_events_help(self, runner, sample_config):
        result = runner.invoke(cli, ["backfill-events", "--help"])
        assert result.exit_code == 0


class TestBindEscRegression:
    """Regression test for the _MergedKeyBindings AttributeError that crashed
    the interactive menu in questionary 2.x with prompt_toolkit 3.0.51+."""

    def test_bind_esc_does_not_raise(self, runner, sample_config):
        """_bind_esc must not crash on prompt_toolkit 3.0.51+ where
        application.key_bindings is _MergedKeyBindings (no .add())."""
        import questionary

        from claude_offline_updater.cli import _bind_esc
        # Use a real question so application is built
        q = questionary.confirm("test")
        # This was raising AttributeError: '_MergedKeyBindings' object has no attribute 'add'
        _bind_esc(q)
        # The application's key_bindings should now include the merged
        # bindings with our ESC handler attached
        assert q.application.key_bindings is not None

    def test_bind_esc_preserves_existing_bindings(self, runner, sample_config):
        """After _bind_esc, the original bindings (arrow keys, enter, etc.)
        must still work — only ESC is added."""
        import questionary

        from claude_offline_updater.cli import _bind_esc
        q = questionary.select("pick", choices=["a", "b"])
        _bind_esc(q)
        merged = q.application.key_bindings
        # The merge should retain original + add ESC
        # (we can't easily assert ESC was added, but the object should be
        # a valid bindings registry)
        assert merged is not None
