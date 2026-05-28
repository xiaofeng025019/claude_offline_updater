from unittest.mock import MagicMock, patch

from claude_offline_updater.config import Machine
from claude_offline_updater.scanner import _get_remote_info, scan_all, scan_local, scan_machine


class TestScanLocal:
    def test_returns_installed_version(self, sample_local):
        with patch("claude_offline_updater.scanner.os.path.islink", return_value=True), \
             patch("claude_offline_updater.scanner.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="Claude 3.5.0\n")
            result = scan_local(sample_local)
            assert result["version"] == "3.5.0"
            assert result["is_local"] is True
            assert result["name"] == "localhost"

    def test_returns_not_installed_no_binary(self, sample_local):
        with patch("claude_offline_updater.scanner.os.path.islink", return_value=False), \
             patch("claude_offline_updater.scanner.os.path.isfile", return_value=False):
            result = scan_local(sample_local)
            assert result["version"] == "Not installed"

    def test_handles_subprocess_exception(self, sample_local):
        with (
            patch("claude_offline_updater.scanner.os.path.islink", return_value=True),
            patch(
                "claude_offline_updater.scanner.subprocess.run",
                side_effect=Exception("timeout"),
            ),
        ):
            result = scan_local(sample_local)
            assert result["version"] == "Not installed"


class TestScanMachine:
    @patch("claude_offline_updater.scanner._get_remote_info", return_value=("2.0.0", "abc123"))
    def test_returns_version_from_remote(self, mock_get_ver, sample_settings, sample_machine):
        result = scan_machine(sample_machine, sample_settings)
        assert result["version"] == "2.0.0"
        assert result["name"] == "test-server"
        assert result["is_local"] is False
        assert result["machine_id"] == "abc123"

    @patch("claude_offline_updater.scanner._get_remote_info", return_value=("Not installed", ""))
    def test_returns_not_installed(self, mock_get_ver, sample_settings, sample_machine):
        result = scan_machine(sample_machine, sample_settings)
        assert result["version"] == "Not installed"


class TestScanAll:
    def test_includes_local_when_enabled(self, sample_settings, sample_local):
        machines = [Machine(name="s1", host="10.0.0.1")]
        with patch("claude_offline_updater.scanner.scan_local") as mock_local, \
             patch("claude_offline_updater.scanner.scan_machine") as mock_machine:
            mock_local.return_value = {
                "name": "localhost", "host": "127.0.0.1", "port": "-",
                "user": "test", "version": "1.0.0", "tags": ["local"],
                "is_local": True,
            }
            mock_machine.return_value = {
                "name": "s1", "host": "10.0.0.1", "port": 22,
                "user": "root", "version": "2.0.0", "tags": [],
                "is_local": False,
            }
            results = scan_all(machines, sample_settings, sample_local)
            mock_local.assert_called_once()
            assert any(r["is_local"] for r in results)

    def test_excludes_local_when_none(self, sample_settings):
        machines = [Machine(name="s1", host="10.0.0.1")]
        with patch("claude_offline_updater.scanner.scan_machine") as mock_machine:
            mock_machine.return_value = {
                "name": "s1", "host": "10.0.0.1", "port": 22,
                "user": "root", "version": "2.0.0", "tags": [],
                "is_local": False,
            }
            results = scan_all(machines, sample_settings, local=None)
            assert not any(r["is_local"] for r in results)

    def test_sorts_local_first(self, sample_settings, sample_local):
        machines = [Machine(name="s1", host="10.0.0.1")]
        with patch("claude_offline_updater.scanner.scan_local") as mock_local, \
             patch("claude_offline_updater.scanner.scan_machine") as mock_machine:
            mock_local.return_value = {
                "name": "localhost", "host": "127.0.0.1", "port": "-",
                "user": "test", "version": "1.0.0", "tags": ["local"],
                "is_local": True,
            }
            mock_machine.return_value = {
                "name": "s1", "host": "10.0.0.1", "port": 22,
                "user": "root", "version": "2.0.0", "tags": [],
                "is_local": False,
            }
            results = scan_all(machines, sample_settings, sample_local)
            assert results[0]["is_local"] is True

    def test_handles_scan_exception_gracefully(self, sample_settings, sample_local):
        machines = [Machine(name="s1", host="10.0.0.1")]
        with patch("claude_offline_updater.scanner.scan_local") as mock_local, \
             patch("claude_offline_updater.scanner.scan_machine", side_effect=Exception("fail")):
            mock_local.return_value = {
                "name": "localhost", "host": "127.0.0.1", "port": "-",
                "user": "test", "version": "1.0.0", "tags": ["local"],
                "is_local": True,
            }
            results = scan_all(machines, sample_settings, sample_local)
            assert len(results) == 2
            failed = [r for r in results if not r["is_local"]]
            assert len(failed) == 1
            assert failed[0]["version"] == "Connection failed"


class TestGetRemoteVersion:
    def _make_machine(self):
        return Machine(name="test-server", host="192.168.1.100", port=22, user="root")

    @patch("claude_offline_updater.scanner.paramiko.SSHClient")
    def test_returns_parsed_version(self, mock_client_cls, sample_settings):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        stdout = MagicMock()
        stdout.read.return_value = b"Claude 3.5.0\n"
        mock_client.exec_command.return_value = (MagicMock(), stdout, MagicMock())

        version, machine_id = _get_remote_info(self._make_machine(), sample_settings)
        assert version == "3.5.0"

    @patch("claude_offline_updater.scanner.paramiko.SSHClient")
    def test_returns_not_installed_on_empty_output(self, mock_client_cls, sample_settings):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        stdout = MagicMock()
        stdout.read.return_value = b""
        mock_client.exec_command.return_value = (MagicMock(), stdout, MagicMock())

        version, machine_id = _get_remote_info(self._make_machine(), sample_settings)
        assert version == "Not installed"

    @patch("claude_offline_updater.scanner.paramiko.SSHClient")
    def test_returns_conn_failed_on_ssh_exception(self, mock_client_cls, sample_settings):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.connect.side_effect = Exception("connection refused")

        version, machine_id = _get_remote_info(self._make_machine(), sample_settings)
        assert version == "Connection failed"

    @patch("claude_offline_updater.scanner.paramiko.SSHClient")
    def test_client_closed_on_success(self, mock_client_cls, sample_settings):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        stdout = MagicMock()
        stdout.read.return_value = b"1.0.0\n"
        mock_client.exec_command.return_value = (MagicMock(), stdout, MagicMock())

        _get_remote_info(self._make_machine(), sample_settings)
        mock_client.close.assert_called_once()

    @patch("claude_offline_updater.scanner.paramiko.SSHClient")
    def test_client_closed_on_exception(self, mock_client_cls, sample_settings):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.connect.side_effect = Exception("fail")

        _get_remote_info(self._make_machine(), sample_settings)
        mock_client.close.assert_called_once()
