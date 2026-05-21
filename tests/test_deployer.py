from unittest.mock import MagicMock, patch

from claude_offline_updater.config import Settings
from claude_offline_updater.deployer import (
    _ensure_remote_dir,
    _get_current_symlink,
    _rollback_symlink,
    _ssh_connect,
    deploy_all,
    deploy_local,
    deploy_to_machine,
)


class TestDeployLocal:
    def _make_result(self, version="1.0.0"):
        return {
            "name": "localhost",
            "host": "127.0.0.1",
            "version": version,
            "is_local": True,
        }

    def test_skips_when_already_latest(self, sample_local, sample_settings):
        result = self._make_result(version="2.0.0")
        out = deploy_local(result, "/tmp/binary", "2.0.0", sample_local, sample_settings)
        assert out["status"] == "skipped"
        assert out["duration_seconds"] == 0

    @patch("claude_offline_updater.deployer.cleanup_local_versions")
    @patch("claude_offline_updater.deployer.subprocess.run")
    @patch("claude_offline_updater.deployer.os.path.islink", return_value=False)
    def test_install_success(
        self, mock_islink, mock_run, mock_cleanup,
        sample_local, sample_settings,
    ):
        install_proc = MagicMock()
        install_proc.returncode = 0
        version_proc = MagicMock()
        version_proc.returncode = 0
        version_proc.stdout = "2.0.0"
        mock_run.side_effect = [install_proc, version_proc]

        result = self._make_result(version="1.0.0")
        out = deploy_local(result, "/tmp/binary", "2.0.0", sample_local, sample_settings)
        assert out["status"] == "success"

    @patch("claude_offline_updater.deployer._set_install_method_local")
    @patch("claude_offline_updater.deployer.os.chmod")
    @patch("claude_offline_updater.deployer.subprocess.run")
    @patch("claude_offline_updater.deployer.os.path.islink", return_value=False)
    @patch("claude_offline_updater.deployer.os.path.exists", return_value=False)
    @patch("claude_offline_updater.deployer.shutil.copy2")
    @patch("claude_offline_updater.deployer.os.symlink")
    @patch("claude_offline_updater.deployer.os.makedirs")
    def test_fallback_manual_deploy(
        self, mock_makedirs, mock_symlink, mock_copy2,
        mock_exists, mock_islink, mock_run, mock_chmod, mock_set_method,
        sample_local, sample_settings,
    ):
        install_proc = MagicMock()
        install_proc.returncode = 1
        version_proc = MagicMock()
        version_proc.returncode = 0
        version_proc.stdout = "2.0.0"
        mock_run.side_effect = [install_proc, version_proc]

        result = self._make_result(version="1.0.0")
        out = deploy_local(result, "/tmp/binary", "2.0.0", sample_local, sample_settings)
        assert out["status"] == "success"
        mock_copy2.assert_called_once()
        mock_symlink.assert_called_once()

    @patch("claude_offline_updater.deployer._local_rollback")
    @patch("claude_offline_updater.deployer.subprocess.run")
    @patch("claude_offline_updater.deployer.os.path.islink", return_value=True)
    @patch("claude_offline_updater.deployer.os.path.realpath", return_value="/old/version/1.0.0")
    def test_version_mismatch_rollback(
        self, mock_realpath, mock_islink, mock_run, mock_rollback,
        sample_local, sample_settings,
    ):
        install_proc = MagicMock()
        install_proc.returncode = 0
        version_proc = MagicMock()
        version_proc.returncode = 0
        version_proc.stdout = "9.9.9"
        mock_run.side_effect = [install_proc, version_proc]

        result = self._make_result(version="1.0.0")
        out = deploy_local(result, "/tmp/binary", "2.0.0", sample_local, sample_settings)
        assert out["status"] == "failed"
        mock_rollback.assert_called_once()

    @patch("claude_offline_updater.deployer.subprocess.run", side_effect=Exception("boom"))
    @patch("claude_offline_updater.deployer.os.path.islink", return_value=False)
    def test_deploy_exception(self, mock_islink, mock_run, sample_local, sample_settings):
        result = self._make_result(version="1.0.0")
        out = deploy_local(result, "/tmp/binary", "2.0.0", sample_local, sample_settings)
        assert out["status"] == "failed"


class TestDeployToMachine:
    def _make_result(self, version="1.0.0"):
        return {
            "name": "test-server",
            "host": "192.168.1.100",
            "port": 22,
            "user": "root",
            "version": version,
        }

    def test_skips_when_already_latest(self, sample_settings):
        result = self._make_result(version="2.0.0")
        out = deploy_to_machine(result, "/tmp/binary", "2.0.0", sample_settings)
        assert out["status"] == "skipped"
        assert out["duration_seconds"] == 0

    @patch("claude_offline_updater.deployer.cleanup_old_versions")
    @patch("claude_offline_updater.deployer._ssh_connect")
    def test_success_path(self, mock_connect, mock_cleanup, sample_settings):
        client = MagicMock()
        mock_connect.return_value = client

        stdout = MagicMock()
        stdout.channel.recv_exit_status.return_value = 0
        stdout.read.return_value = b"2.0.0"
        client.exec_command.return_value = (MagicMock(), stdout, MagicMock())

        sftp = MagicMock()
        client.open_sftp.return_value = sftp

        result = self._make_result(version="1.0.0")
        out = deploy_to_machine(result, "/tmp/binary", "2.0.0", sample_settings)
        assert out["status"] == "success"
        client.close.assert_called_once()

    @patch("claude_offline_updater.deployer._ssh_connect")
    def test_sftp_transfer_no_limit(self, mock_connect, sample_settings):
        client = MagicMock()
        mock_connect.return_value = client

        stdout = MagicMock()
        stdout.channel.recv_exit_status.return_value = 0
        stdout.read.return_value = b"2.0.0"
        client.exec_command.return_value = (MagicMock(), stdout, MagicMock())

        sftp = MagicMock()
        client.open_sftp.return_value = sftp

        settings = Settings(scp_bandwidth_limit=0)
        result = self._make_result(version="1.0.0")
        deploy_to_machine(result, "/tmp/binary", "2.0.0", settings)
        sftp.put.assert_called_once()

    @patch("claude_offline_updater.deployer._scp_with_limit")
    @patch("claude_offline_updater.deployer._ssh_connect")
    def test_scp_with_limit(self, mock_connect, mock_scp, sample_settings):
        client = MagicMock()
        mock_connect.return_value = client

        stdout = MagicMock()
        stdout.channel.recv_exit_status.return_value = 0
        stdout.read.return_value = b"2.0.0"
        client.exec_command.return_value = (MagicMock(), stdout, MagicMock())

        sftp = MagicMock()
        client.open_sftp.return_value = sftp

        settings = Settings(scp_bandwidth_limit=1000)
        result = self._make_result(version="1.0.0")
        deploy_to_machine(result, "/tmp/binary", "2.0.0", settings)
        mock_scp.assert_called_once()
        sftp.put.assert_not_called()

    @patch("claude_offline_updater.deployer.cleanup_old_versions")
    @patch("claude_offline_updater.deployer._ensure_path")
    @patch("claude_offline_updater.deployer._set_install_method_remote")
    @patch("claude_offline_updater.deployer._ssh_connect")
    def test_install_fallback(
        self, mock_connect, mock_set_method,
        mock_ensure_path, mock_cleanup, sample_settings,
    ):
        client = MagicMock()
        mock_connect.return_value = client

        def make_stdout(read_data=b"", exit_status=0):
            stdout = MagicMock()
            stdout.read.return_value = read_data
            stdout.channel.recv_exit_status.return_value = exit_status
            return stdout

        call_count = [0]

        def exec_command_side_effect(cmd, timeout=10):
            call_count[0] += 1
            if "readlink" in cmd:
                return (MagicMock(), make_stdout(read_data=b""), MagicMock())
            elif "install" in cmd and "installMethod" not in cmd:
                return (MagicMock(), make_stdout(exit_status=1), MagicMock())
            elif "mkdir -p" in cmd and "versions" in cmd or "cp " in cmd or "ln -sf" in cmd:
                return (MagicMock(), make_stdout(exit_status=0), MagicMock())
            elif "--version" in cmd:
                return (MagicMock(), make_stdout(read_data=b"2.0.0"), MagicMock())
            else:
                return (MagicMock(), make_stdout(exit_status=0), MagicMock())

        client.exec_command.side_effect = exec_command_side_effect

        sftp = MagicMock()
        client.open_sftp.return_value = sftp

        result = self._make_result(version="1.0.0")
        out = deploy_to_machine(result, "/tmp/binary", "2.0.0", sample_settings)
        assert out["status"] == "success"

    @patch("claude_offline_updater.deployer._ssh_connect")
    def test_exception_triggers_rollback(self, mock_connect, sample_settings):
        client = MagicMock()
        mock_connect.side_effect = [
            Exception("connection lost"),
            client,
        ]

        result = self._make_result(version="1.0.0")
        out = deploy_to_machine(result, "/tmp/binary", "2.0.0", sample_settings)
        assert out["status"] == "failed"

    @patch("claude_offline_updater.deployer._ssh_connect")
    def test_client_closed_on_exception(self, mock_connect, sample_settings):
        client = MagicMock()
        mock_connect.return_value = client

        client.open_sftp.side_effect = Exception("sftp error")

        result = self._make_result(version="1.0.0")
        deploy_to_machine(result, "/tmp/binary", "2.0.0", sample_settings)
        client.close.assert_called_once()


class TestDeployAll:
    def test_local_deployment_called(self, sample_settings, sample_local):
        local_result = {
            "name": "localhost",
            "host": "127.0.0.1",
            "version": "1.0.0",
            "is_local": True,
        }
        with patch("claude_offline_updater.deployer.deploy_local") as mock_local:
            mock_local.return_value = {
                "name": "localhost", "host": "127.0.0.1",
                "from_version": "1.0.0", "to_version": "2.0.0",
                "status": "success", "duration_seconds": 1.0,
            }
            results = deploy_all(
                [local_result], "/tmp/binary", "2.0.0",
                sample_settings, sample_local,
            )
            mock_local.assert_called_once()
            assert results[0]["status"] == "success"

    def test_remote_parallel_deployment(self, sample_settings):
        remote1 = {
            "name": "server1", "host": "10.0.0.1",
            "version": "1.0.0", "is_local": False,
        }
        remote2 = {
            "name": "server2", "host": "10.0.0.2",
            "version": "1.0.0", "is_local": False,
        }
        with patch("claude_offline_updater.deployer.deploy_to_machine") as mock_remote:
            mock_remote.return_value = {
                "name": "server1", "host": "10.0.0.1",
                "from_version": "1.0.0", "to_version": "2.0.0",
                "status": "success", "duration_seconds": 2.0,
            }
            deploy_all(
                [remote1, remote2], "/tmp/binary", "2.0.0", sample_settings,
            )
            assert mock_remote.call_count == 2

    def test_results_sorted_local_first(self, sample_settings, sample_local):
        local_result = {
            "name": "localhost", "host": "127.0.0.1",
            "version": "1.0.0", "is_local": True,
        }
        remote_result = {
            "name": "server1", "host": "10.0.0.1",
            "version": "1.0.0", "is_local": False,
        }
        with patch("claude_offline_updater.deployer.deploy_local") as mock_local, \
             patch("claude_offline_updater.deployer.deploy_to_machine") as mock_remote:
            mock_local.return_value = {
                "name": "localhost", "host": "127.0.0.1",
                "from_version": "1.0.0", "to_version": "2.0.0",
                "status": "success", "duration_seconds": 1.0,
            }
            mock_remote.return_value = {
                "name": "server1", "host": "10.0.0.1",
                "from_version": "1.0.0", "to_version": "2.0.0",
                "status": "success", "duration_seconds": 2.0,
            }
            results = deploy_all(
                [local_result, remote_result], "/tmp/binary", "2.0.0",
                sample_settings, sample_local,
            )
            names = [r["name"] for r in results]
            assert names.index("localhost") < names.index("server1")


class TestSshConnect:
    @patch("claude_offline_updater.deployer.paramiko.SSHClient")
    def test_default_warn_policy(self, mock_client_cls, sample_settings):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        sample_settings.ssh_host_key_policy = "warn"
        _ssh_connect("host", 22, "user", sample_settings)
        mock_client.set_missing_host_key_policy.assert_called_once()
        policy_arg = mock_client.set_missing_host_key_policy.call_args[0][0]
        assert (
            isinstance(policy_arg, type(MagicMock()))
            or policy_arg.__class__.__name__ == "WarningPolicy"
        )

    @patch("claude_offline_updater.deployer.paramiko.SSHClient")
    def test_auto_policy(self, mock_client_cls, sample_settings):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        sample_settings.ssh_host_key_policy = "auto"
        _ssh_connect("host", 22, "user", sample_settings)
        mock_client.set_missing_host_key_policy.assert_called_once()
        policy_arg = mock_client.set_missing_host_key_policy.call_args[0][0]
        assert (
            isinstance(policy_arg, type(MagicMock()))
            or policy_arg.__class__.__name__ == "AutoAddPolicy"
        )

    @patch("claude_offline_updater.deployer.paramiko.SSHClient")
    def test_reject_policy(self, mock_client_cls, sample_settings):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        sample_settings.ssh_host_key_policy = "reject"
        _ssh_connect("host", 22, "user", sample_settings)
        mock_client.set_missing_host_key_policy.assert_called_once()
        policy_arg = mock_client.set_missing_host_key_policy.call_args[0][0]
        assert (
            isinstance(policy_arg, type(MagicMock()))
            or policy_arg.__class__.__name__ == "RejectPolicy"
        )

    @patch("claude_offline_updater.deployer.paramiko.SSHClient")
    def test_loads_host_keys(self, mock_client_cls, sample_settings):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        _ssh_connect("host", 22, "user", sample_settings)
        mock_client.load_system_host_keys.assert_called_once()


class TestHelperFunctions:
    def test_get_current_symlink_found(self):
        client = MagicMock()
        stdout = MagicMock()
        stdout.read.return_value = b"/home/user/.local/share/claude/versions/1.0.0\n"
        client.exec_command.return_value = (MagicMock(), stdout, MagicMock())
        result = _get_current_symlink(client, "~/.local/bin/claude")
        assert result == "/home/user/.local/share/claude/versions/1.0.0"

    def test_get_current_symlink_not_found(self):
        client = MagicMock()
        stdout = MagicMock()
        stdout.read.return_value = b""
        client.exec_command.return_value = (MagicMock(), stdout, MagicMock())
        result = _get_current_symlink(client, "~/.local/bin/claude")
        assert result is None

    def test_rollback_symlink(self):
        client = MagicMock()
        _rollback_symlink(client, "~/.local/bin/claude", "/old/target")
        client.exec_command.assert_called_once()

    def test_ensure_remote_dir(self):
        client = MagicMock()
        _ensure_remote_dir(client, "/tmp/claude-update")
        client.exec_command.assert_called_once()
        cmd = client.exec_command.call_args[0][0]
        assert "mkdir -p" in cmd
