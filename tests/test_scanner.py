from unittest.mock import MagicMock, patch

from claude_offline_updater.config import Machine
from claude_offline_updater.scanner import (
    _get_remote_info,
    _version_key,
    list_installed_versions_local,
    list_installed_versions_remote,
    scan_all,
    scan_local,
    scan_machine,
)


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


class TestListInstalledVersionsLocal:
    def _patch_expanduser(self, monkeypatch, versions_dir):
        import claude_offline_updater.scanner as scan_mod
        monkeypatch.setattr(
            scan_mod.os.path, "expanduser",
            lambda x: str(versions_dir) if "versions" in x else x,
        )

    def test_lists_executable_versions(self, sample_local, tmp_path, monkeypatch):
        versions_dir = tmp_path / "versions"
        versions_dir.mkdir()
        (versions_dir / "2.0.0").write_bytes(b"\x00" * 4)
        (versions_dir / "1.5.0").write_bytes(b"\x00" * 4)
        (versions_dir / "3.0.0").write_bytes(b"\x00" * 4)
        (versions_dir / "2.0.0").chmod(0o755)
        (versions_dir / "1.5.0").chmod(0o755)
        (versions_dir / "3.0.0").chmod(0o755)

        self._patch_expanduser(monkeypatch, versions_dir)
        result = list_installed_versions_local(sample_local)
        assert result[0] == "3.0.0"
        assert "2.0.0" in result
        assert "1.5.0" in result

    def test_empty_dir(self, sample_local, tmp_path, monkeypatch):
        versions_dir = tmp_path / "versions"
        versions_dir.mkdir()
        self._patch_expanduser(monkeypatch, versions_dir)
        assert list_installed_versions_local(sample_local) == []

    def test_nonexistent_dir(self, sample_local, tmp_path, monkeypatch):
        self._patch_expanduser(monkeypatch, tmp_path / "nope")
        assert list_installed_versions_local(sample_local) == []

    def test_skips_non_executable(self, sample_local, tmp_path, monkeypatch):
        versions_dir = tmp_path / "versions"
        versions_dir.mkdir()
        f = versions_dir / "1.0.0"
        f.write_text("data")
        f.chmod(0o644)

        self._patch_expanduser(monkeypatch, versions_dir)
        result = list_installed_versions_local(sample_local)
        assert result == []

    def test_skips_subdirectories(self, sample_local, tmp_path, monkeypatch):
        versions_dir = tmp_path / "versions"
        versions_dir.mkdir()
        subdir = versions_dir / "1.0.0"
        subdir.mkdir()

        self._patch_expanduser(monkeypatch, versions_dir)
        result = list_installed_versions_local(sample_local)
        assert result == []


class TestListInstalledVersionsRemote:
    @patch("claude_offline_updater.scanner.paramiko.SSHClient")
    def test_returns_sorted_versions(self, mock_client_cls, sample_settings, sample_machine):
        client = MagicMock()
        mock_client_cls.return_value = client
        stdout = MagicMock()
        stdout.read.return_value = b"2.0.0\n1.5.0\n3.0.0\n"
        client.exec_command.return_value = (MagicMock(), stdout, MagicMock())

        result = list_installed_versions_remote(sample_machine, sample_settings)
        assert result == ["3.0.0", "2.0.0", "1.5.0"]
        client.close.assert_called_once()

    @patch("claude_offline_updater.scanner.paramiko.SSHClient")
    def test_empty_output(self, mock_client_cls, sample_settings, sample_machine):
        client = MagicMock()
        mock_client_cls.return_value = client
        stdout = MagicMock()
        stdout.read.return_value = b""
        client.exec_command.return_value = (MagicMock(), stdout, MagicMock())

        result = list_installed_versions_remote(sample_machine, sample_settings)
        assert result == []

    @patch("claude_offline_updater.scanner.paramiko.SSHClient")
    def test_ssh_exception(self, mock_client_cls, sample_settings, sample_machine):
        client = MagicMock()
        mock_client_cls.return_value = client
        client.connect.side_effect = Exception("fail")

        result = list_installed_versions_remote(sample_machine, sample_settings)
        assert result == []


class TestVersionKey:
    def test_sorts_correctly(self):
        versions = ["2.0.0", "1.10.0", "1.9.0", "3.0.0"]
        versions.sort(key=_version_key, reverse=True)
        assert versions == ["3.0.0", "2.0.0", "1.10.0", "1.9.0"]

    def test_handles_non_numeric(self):
        assert _version_key("1.0.0-beta") == (1, 0, 0)
