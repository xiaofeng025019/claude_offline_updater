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
