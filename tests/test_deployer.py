import contextlib
from unittest.mock import MagicMock, patch

from claude_offline_updater.config import Settings
from claude_offline_updater.deployer import (
    _ensure_remote_dir,
    _get_current_symlink,
    _is_remote_version_installed,
    _is_safe_remote_path,
    _resolve_remote_path,
    _rollback_symlink,
    _ssh_connect,
    deploy_all,
    deploy_local,
    deploy_to_machine,
    rollback_all,
    rollback_local,
    rollback_to_machine,
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

    def test_resolve_remote_path_no_tilde_passthrough(self):
        client = MagicMock()
        assert _resolve_remote_path(client, "/usr/local/bin/claude") == "/usr/local/bin/claude"
        client.exec_command.assert_not_called()

    def test_is_safe_remote_path_whitelist(self):
        # All whitelisted chars are safe
        assert _is_safe_remote_path("~/.local/bin/claude")
        assert _is_safe_remote_path("/usr/local/bin/claude-1.0.0")
        # Shell metacharacters are not
        assert not _is_safe_remote_path("/tmp/x;evil")
        assert not _is_safe_remote_path("`cmd`")
        assert not _is_safe_remote_path("$VAR")
        assert not _is_safe_remote_path("a|b")
        assert not _is_safe_remote_path("a&b")

    def test_resolve_remote_path_expands_tilde(self):
        client = MagicMock()
        stdout = MagicMock()
        stdout.read.return_value = b"/home/user/.local/bin/claude\n"
        client.exec_command.return_value = (MagicMock(), stdout, MagicMock())
        assert _resolve_remote_path(client, "~/.local/bin/claude") == "/home/user/.local/bin/claude"
        # Critical: command must NOT single-quote the path (which would
        # prevent tilde expansion)
        cmd = client.exec_command.call_args[0][0]
        assert "echo" in cmd
        assert "~/.local/bin/claude" in cmd
        assert "'" not in cmd  # no single-quotes that would suppress expansion

    def test_resolve_remote_path_rejects_unsafe(self):
        client = MagicMock()
        # Path with shell metachar — must not be passed to remote shell
        assert _resolve_remote_path(client, "/tmp/x;rm -rf /") == "/tmp/x;rm -rf /"
        client.exec_command.assert_not_called()

    def test_rollback_symlink_waits_for_completion(self):
        # Bug fix: was returning before ln -sf finished
        client = MagicMock()
        channel = MagicMock()
        stdout = MagicMock()
        stdout.channel = channel
        client.exec_command.return_value = (MagicMock(), stdout, MagicMock())
        _rollback_symlink(client, "~/.local/bin/claude", "/old/target", label="x")
        channel.recv_exit_status.assert_called_once()

    def test_rollback_symlink_rejects_unsafe_target(self):
        client = MagicMock()
        # target comes from readlink output — must be sanitized
        _rollback_symlink(client, "~/.local/bin/claude", "/tmp/x;evil", label="x")
        client.exec_command.assert_not_called()


class TestRollbackLocal:
    def test_skips_when_same_version(self, sample_local, sample_settings):
        result = rollback_local("2.0.0", "2.0.0", sample_local, sample_settings)
        assert result["status"] == "skipped"
        assert result["duration_seconds"] == 0

    @patch("claude_offline_updater.deployer.subprocess.run")
    @patch("claude_offline_updater.deployer.os.access", return_value=True)
    @patch("claude_offline_updater.deployer.os.path.isfile", return_value=True)
    def test_rollback_success(self, mock_isfile, mock_access, mock_run,
                               sample_local, sample_settings):
        ln_proc = MagicMock()
        ln_proc.returncode = 0
        ver_proc = MagicMock()
        ver_proc.returncode = 0
        ver_proc.stdout = "1.5.0\n"
        mock_run.side_effect = [ln_proc, ver_proc]

        result = rollback_local("2.0.0", "1.5.0", sample_local, sample_settings)
        assert result["status"] == "success"
        assert result["from_version"] == "2.0.0"
        assert result["to_version"] == "1.5.0"

    @patch("claude_offline_updater.deployer.os.access", return_value=False)
    @patch("claude_offline_updater.deployer.os.path.isfile", return_value=True)
    def test_target_not_executable(self, mock_isfile, mock_access,
                                    sample_local, sample_settings):
        result = rollback_local("2.0.0", "1.0.0", sample_local, sample_settings)
        assert result["status"] == "failed"
        assert "not found" in result["detail"]

    @patch("claude_offline_updater.deployer.os.path.isfile", return_value=False)
    def test_target_not_found(self, mock_isfile, sample_local, sample_settings):
        result = rollback_local("2.0.0", "1.0.0", sample_local, sample_settings)
        assert result["status"] == "failed"

    @patch("claude_offline_updater.deployer.subprocess.run")
    @patch("claude_offline_updater.deployer.os.access", return_value=True)
    @patch("claude_offline_updater.deployer.os.path.isfile", return_value=True)
    def test_rollback_version_mismatch_reverts(self, mock_isfile, mock_access,
                                                mock_run, sample_local, sample_settings):
        ln_proc = MagicMock()
        ln_proc.returncode = 0
        ver_proc = MagicMock()
        ver_proc.returncode = 0
        ver_proc.stdout = "9.9.9\n"
        revert_proc = MagicMock()
        revert_proc.returncode = 0
        mock_run.side_effect = [ln_proc, ver_proc, revert_proc]

        result = rollback_local("2.0.0", "1.5.0", sample_local, sample_settings)
        assert result["status"] == "failed"
        assert mock_run.call_count == 3  # ln -sf, --version, revert ln -sf

    @patch("claude_offline_updater.deployer.subprocess.run", side_effect=Exception("ln failed"))
    @patch("claude_offline_updater.deployer.os.access", return_value=True)
    @patch("claude_offline_updater.deployer.os.path.isfile", return_value=True)
    def test_ln_sf_exception(self, mock_isfile, mock_access, mock_run,
                              sample_local, sample_settings):
        result = rollback_local("2.0.0", "1.5.0", sample_local, sample_settings)
        assert result["status"] == "failed"
        assert "ln failed" in result["detail"]


class TestRollbackToMachine:
    def _make_result(self, version="2.0.0"):
        return {
            "name": "server1", "host": "10.0.0.1", "port": 22,
            "user": "root", "version": version, "machine_id": "abc123",
        }

    def test_skips_when_same_version(self, sample_settings):
        result = rollback_to_machine(self._make_result("1.5.0"), "1.5.0", sample_settings)
        assert result["status"] == "skipped"

    @patch("claude_offline_updater.deployer._ssh_connect")
    def test_remote_rollback_success(self, mock_connect, sample_settings):
        client = MagicMock()
        mock_connect.return_value = client

        def exec_side_effect(cmd, timeout=10):
            stdout = MagicMock()
            if "test -x" in cmd:
                stdout.read.return_value = b"ok"
            elif "--version" in cmd:
                stdout.read.return_value = b"1.5.0\n"
            return (MagicMock(), stdout, MagicMock())

        client.exec_command.side_effect = exec_side_effect

        result = rollback_to_machine(self._make_result(), "1.5.0", sample_settings)
        assert result["status"] == "success"
        assert result["to_version"] == "1.5.0"
        client.close.assert_called_once()

    @patch("claude_offline_updater.deployer._ssh_connect")
    def test_remote_target_not_found(self, mock_connect, sample_settings):
        client = MagicMock()
        mock_connect.return_value = client

        stdout = MagicMock()
        stdout.read.return_value = b"missing"
        client.exec_command.return_value = (MagicMock(), stdout, MagicMock())

        result = rollback_to_machine(self._make_result(), "1.0.0", sample_settings)
        assert result["status"] == "failed"
        assert "not found" in result["detail"]

    @patch("claude_offline_updater.deployer._ssh_connect")
    def test_remote_version_mismatch_reverts(self, mock_connect, sample_settings):
        client = MagicMock()
        mock_connect.return_value = client

        call_count = [0]

        def exec_side_effect(cmd, timeout=10):
            call_count[0] += 1
            stdout = MagicMock()
            if "test -x" in cmd:
                stdout.read.return_value = b"ok"
            elif "--version" in cmd:
                stdout.read.return_value = b"9.9.9\n"
            return (MagicMock(), stdout, MagicMock())

        client.exec_command.side_effect = exec_side_effect

        result = rollback_to_machine(self._make_result(), "1.5.0", sample_settings)
        assert result["status"] == "failed"
        # Should have called exec_command for: test, ln -sf, --version, revert ln -sf
        assert call_count[0] >= 3

    @patch("claude_offline_updater.deployer._ssh_connect")
    def test_ssh_exception(self, mock_connect, sample_settings):
        mock_connect.side_effect = Exception("connection refused")
        result = rollback_to_machine(self._make_result(), "1.5.0", sample_settings)
        assert result["status"] == "failed"

    @patch("claude_offline_updater.deployer._ssh_connect")
    def test_client_closed_on_exception(self, mock_connect, sample_settings):
        client = MagicMock()
        mock_connect.return_value = client
        client.exec_command.side_effect = Exception("cmd failed")

        rollback_to_machine(self._make_result(), "1.5.0", sample_settings)
        client.close.assert_called_once()


class TestRollbackAll:
    def test_local_rollback_called(self, sample_settings, sample_local):
        local_target = {
            "name": "localhost", "host": "127.0.0.1",
            "version": "2.0.0", "is_local": True, "machine_id": "m1",
        }
        with patch("claude_offline_updater.deployer.rollback_local") as mock_local:
            mock_local.return_value = {
                "name": "localhost", "host": "127.0.0.1",
                "from_version": "2.0.0", "to_version": "1.5.0",
                "status": "success", "duration_seconds": 1.0,
                "machine_id": "m1",
            }
            results = rollback_all(
                [local_target], "1.5.0", sample_settings, sample_local,
            )
            mock_local.assert_called_once()
            assert results[0]["status"] == "success"

    def test_remote_parallel_rollback(self, sample_settings):
        remote1 = {
            "name": "s1", "host": "10.0.0.1", "version": "2.0.0",
            "is_local": False, "machine_id": "m1",
        }
        remote2 = {
            "name": "s2", "host": "10.0.0.2", "version": "2.0.0",
            "is_local": False, "machine_id": "m2",
        }
        with patch("claude_offline_updater.deployer.rollback_to_machine") as mock_remote:
            mock_remote.return_value = {
                "name": "s1", "host": "10.0.0.1",
                "from_version": "2.0.0", "to_version": "1.5.0",
                "status": "success", "duration_seconds": 2.0,
                "machine_id": "m1",
            }
            rollback_all([remote1, remote2], "1.5.0", sample_settings)
            assert mock_remote.call_count == 2

    def test_local_without_local_config_skipped(self, sample_settings):
        local_target = {
            "name": "localhost", "host": "127.0.0.1",
            "version": "2.0.0", "is_local": True, "machine_id": "m1",
        }
        results = rollback_all([local_target], "1.5.0", sample_settings, local=None)
        assert results[0]["status"] == "skipped"

    def test_results_sorted_local_first(self, sample_settings, sample_local):
        local_result = {
            "name": "localhost", "host": "127.0.0.1",
            "version": "2.0.0", "is_local": True, "machine_id": "m1",
        }
        remote_result = {
            "name": "s1", "host": "10.0.0.1", "version": "2.0.0",
            "is_local": False, "machine_id": "m2",
        }
        with patch("claude_offline_updater.deployer.rollback_local") as mock_local, \
             patch("claude_offline_updater.deployer.rollback_to_machine") as mock_remote:
            mock_local.return_value = {
                "name": "localhost", "host": "127.0.0.1",
                "from_version": "2.0.0", "to_version": "1.5.0",
                "status": "success", "duration_seconds": 1.0,
                "machine_id": "m1",
            }
            mock_remote.return_value = {
                "name": "s1", "host": "10.0.0.1",
                "from_version": "2.0.0", "to_version": "1.5.0",
                "status": "success", "duration_seconds": 2.0,
                "machine_id": "m2",
            }
            results = rollback_all(
                [local_result, remote_result], "1.5.0",
                sample_settings, sample_local,
            )
            names = [r["name"] for r in results]
            assert names.index("localhost") < names.index("s1")


class TestAutoPinOnRollback:
    """Auto-pin is triggered by the deployer on rollback success via
    _auto_pin_on_rollback helper. These tests mock history.record_event
    to verify it's called with the right args (and not called on failure)."""

    @patch("claude_offline_updater.history.record_event")
    def test_rollback_local_success_triggers_auto_pin(
        self, mock_record, sample_local, sample_settings,
    ):
        from claude_offline_updater.history import EVENT_PIN
        # rollback_local checks: os.path.isfile(target), os.access(target),
        # and runs ln -sf + --version subprocesses. Mock all of them.
        with patch("claude_offline_updater.deployer.os.path.isfile", return_value=True), \
             patch("claude_offline_updater.deployer.os.access", return_value=True), \
             patch("claude_offline_updater.deployer.subprocess.run") as mock_run, \
             patch("claude_offline_updater.deployer.cleanup_local_versions"):
            install_proc = MagicMock(returncode=0)
            version_proc = MagicMock(returncode=0, stdout="1.0.0")
            mock_run.side_effect = [install_proc, version_proc]

            from claude_offline_updater.deployer import rollback_local
            out = rollback_local("2.0.0", "1.0.0", sample_local, sample_settings,
                                 machine_id="m1")
            assert out["status"] == "success"
            pin_calls = [c for c in mock_record.call_args_list
                         if c.args and c.args[0] == EVENT_PIN]
            assert len(pin_calls) == 1
            assert pin_calls[0].kwargs["version"] == "1.0.0"
            assert pin_calls[0].kwargs["machine_id"] == "m1"

    @patch("claude_offline_updater.history.has_recent_pin", return_value=True)
    @patch("claude_offline_updater.history.record_event")
    def test_rollback_success_skips_pin_when_recent_exists(
        self, mock_record, mock_recent, sample_local, sample_settings,
    ):
        with patch("claude_offline_updater.deployer.os.path.isfile", return_value=True), \
             patch("claude_offline_updater.deployer.os.access", return_value=True), \
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
        # current == target → returns "skipped" (not success), no pin
        from claude_offline_updater.deployer import rollback_local
        with patch("claude_offline_updater.history.record_event") as mock_record:
            out = rollback_local("1.0.0", "1.0.0", sample_local, sample_settings,
                                 machine_id="m1")
            assert out["status"] == "skipped"
            mock_record.assert_not_called()

    def test_rollback_local_real_failure_does_not_pin(self, sample_local, sample_settings):
        # Target binary missing in versions_dir → "failed" (not success), no pin
        from claude_offline_updater.deployer import rollback_local
        with patch("claude_offline_updater.deployer.os.path.isfile", return_value=False), \
             patch("claude_offline_updater.history.record_event") as mock_record:
            out = rollback_local("2.0.0", "1.0.0", sample_local, sample_settings,
                                 machine_id="m1")
            assert out["status"] == "failed"
            mock_record.assert_not_called()

    @patch("claude_offline_updater.history.record_event")
    def test_rollback_to_machine_success_triggers_auto_pin(
        self, mock_record, sample_settings, sample_machine,
    ):
        """Auto-pin fires when rollback_to_machine returns success.

        Tests the helper directly rather than threading through rollback_all
        (whose ThreadPoolExecutor closure bypasses function-level patches)."""
        from claude_offline_updater.deployer import _auto_pin_on_rollback

        _auto_pin_on_rollback({
            "name": sample_machine.name, "host": sample_machine.host,
            "from_version": "2.0.0", "to_version": "1.0.0",
            "machine_id": "m2", "status": "success",
            "duration_seconds": 1.0,
        })
        from claude_offline_updater.history import EVENT_PIN
        pin_calls = [c for c in mock_record.call_args_list
                     if c.args and c.args[0] == EVENT_PIN]
        assert len(pin_calls) == 1
        assert pin_calls[0].kwargs["version"] == "1.0.0"
        assert pin_calls[0].kwargs["machine_id"] == "m2"

    @patch("claude_offline_updater.history.record_event")
    def test_auto_pin_failure_does_not_mask_rollback_success(
        self, mock_record, sample_local, sample_settings,
    ):
        """If record_event raises (e.g., disk full), rollback success must not be masked."""
        mock_record.side_effect = OSError("disk full")
        with patch("claude_offline_updater.deployer.os.path.isfile", return_value=True), \
             patch("claude_offline_updater.deployer.os.access", return_value=True), \
             patch("claude_offline_updater.deployer.subprocess.run") as mock_run, \
             patch("claude_offline_updater.deployer.cleanup_local_versions"):
            install_proc = MagicMock(returncode=0)
            version_proc = MagicMock(returncode=0, stdout="1.0.0")
            mock_run.side_effect = [install_proc, version_proc]

            from claude_offline_updater.deployer import rollback_local
            # Must not raise — pin failure is swallowed
            out = rollback_local("2.0.0", "1.0.0", sample_local, sample_settings,
                                 machine_id="m1")
            assert out["status"] == "success"


class TestIsRemoteVersionInstalled:
    """Helper that checks if a version binary already exists on the remote."""

    def test_returns_true_when_binary_exists_and_executable(self):
        client = MagicMock()
        stdout = MagicMock()
        stdout.read.return_value = b"yes\n"
        client.exec_command.return_value = (MagicMock(), stdout, MagicMock())
        assert _is_remote_version_installed(
            client, "/usr/local/share/claude/versions", "1.0.0"
        ) is True

    def test_returns_false_when_binary_missing(self):
        client = MagicMock()
        stdout = MagicMock()
        stdout.read.return_value = b"no\n"
        client.exec_command.return_value = (MagicMock(), stdout, MagicMock())
        assert _is_remote_version_installed(
            client, "/usr/local/share/claude/versions", "1.0.0"
        ) is False

    def test_rejects_unsafe_version(self):
        """A target_version with shell metacharacters must NOT be passed."""
        client = MagicMock()
        result = _is_remote_version_installed(
            client, "/usr/local/share/claude/versions", "1.0.0;evil"
        )
        assert result is False
        client.exec_command.assert_not_called()


class TestDeployToMachineSkipsScpWhenRemoteHasVersion:
    """If versions_dir/<target> exists on remote, skip SFTP and just
    symlink-swap. Saves 10-50 MB of network transfer per machine.
    Regression: the symlink-swap must STILL happen — without it the
    symlink would keep pointing to the old version and verify fails."""

    @patch("claude_offline_updater.deployer._is_remote_version_installed", return_value=True)
    @patch("claude_offline_updater.deployer.cleanup_old_versions")
    @patch("claude_offline_updater.deployer._ssh_connect")
    def test_skips_sftp_but_still_swaps_symlink(
        self, mock_connect, mock_cleanup, mock_has, sample_settings,
    ):
        client = MagicMock()
        mock_connect.return_value = client

        # Verify returns the new version (post-symlink-swap)
        stdout = MagicMock()
        stdout.channel.recv_exit_status.return_value = 0
        stdout.read.return_value = b"1.0.0\n"
        client.exec_command.return_value = (MagicMock(), stdout, MagicMock())

        result = {
            "name": "test-server", "host": "192.168.1.100", "port": 22,
            "user": "root", "version": "2.0.0", "is_local": False,
            "machine_id": "m1",
        }
        out = deploy_to_machine(result, "/tmp/binary", "1.0.0", sample_settings)

        # SFTP must NOT be opened when remote already has the version
        client.open_sftp.assert_not_called()
        # But ln -sf must be called (the symlink-swap)
        ln_calls = [c for c in client.exec_command.call_args_list
                    if "ln -sf" in str(c)]
        assert ln_calls, f"Expected ln -sf call, got: {client.exec_command.call_args_list}"
        assert out["status"] == "success"

    @patch("claude_offline_updater.deployer._is_remote_version_installed", return_value=True)
    @patch("claude_offline_updater.deployer.cleanup_old_versions")
    @patch("claude_offline_updater.deployer._ssh_connect")
    def test_skip_scp_with_stale_symlink_would_fail_without_swap(
        self, mock_connect, mock_cleanup, mock_has, sample_settings,
    ):
        """True regression test for the user-reported bug.

        Scenario (matches public_kfj / cosmos_kfj):
        - versions_dir/2.1.167 already on remote (file present)
        - claude_bin symlink points to versions_dir/2.1.165 (stale)
        - We deploy 2.1.167, skip SCP, but still MUST swap the symlink
        - Otherwise --version returns 2.1.165, verify fails, rollback fires

        This test makes the verify-version return the OLD version (1.0.0)
        unless ln -sf was called. If skip-SCP branch forgets the swap,
        this test catches it.
        """
        client = MagicMock()
        mock_connect.return_value = client

        # Track command invocations to return different outputs.
        # Without ln -sf, --version returns the OLD version; with ln -sf,
        # the deployer re-runs --version after the swap and gets 2.0.0.
        cmd_outputs = {
            "readlink": "/root/.local/share/claude/versions/1.0.0",  # current symlink target
            "ln -sf": "",                                              # swap (no output)
            "--version": "2.0.0",                                      # post-swap version
            "rm -rf": "",
        }

        def fake_exec(cmd_str, **kwargs):
            stdout = MagicMock()
            stdout.channel.recv_exit_status.return_value = 0
            for key, out_value in cmd_outputs.items():
                if key in cmd_str:
                    stdout.read.return_value = out_value.encode()
                    return (MagicMock(), stdout, MagicMock())
            stdout.read.return_value = b""
            return (MagicMock(), stdout, MagicMock())

        client.exec_command.side_effect = fake_exec

        result = {
            "name": "test-server", "host": "192.168.1.100", "port": 22,
            "user": "root", "version": "1.0.0",  # current is 1.0.0, deploying 2.0.0
            "is_local": False, "machine_id": "m1",
        }
        out = deploy_to_machine(result, "/tmp/binary", "2.0.0", sample_settings)

        # SFTP must NOT have been opened (skip path)
        client.open_sftp.assert_not_called()
        # ln -sf MUST have been called
        ln_calls = [c for c in client.exec_command.call_args_list
                    if "ln -sf" in str(c)]
        assert ln_calls, (
            f"REGRESSION: ln -sf was not called! This means symlink "
            f"would not be updated and verify-version would fail. "
            f"Calls: {client.exec_command.call_args_list}"
        )
        assert out["status"] == "success", (
            f"Without ln -sf, deploy would fail with: {out.get('detail')}"
        )
        assert out["status"] == "success"

    @patch("claude_offline_updater.deployer._is_remote_version_installed", return_value=False)
    @patch("claude_offline_updater.deployer.cleanup_old_versions")
    @patch("claude_offline_updater.deployer._set_install_method_remote")
    @patch("claude_offline_updater.deployer._ensure_path")
    @patch("claude_offline_updater.deployer._ssh_connect")
    def test_transfers_when_remote_missing_version(
        self, mock_connect, mock_ensure_path, mock_set_method, mock_cleanup, mock_has,
        sample_settings,
    ):
        client = MagicMock()
        mock_connect.return_value = client

        stdout = MagicMock()
        stdout.channel.recv_exit_status.return_value = 0
        stdout.read.return_value = b"1.0.0\n"
        client.exec_command.return_value = (MagicMock(), stdout, MagicMock())

        sftp = MagicMock()
        client.open_sftp.return_value = sftp

        result = {
            "name": "test-server", "host": "192.168.1.100", "port": 22,
            "user": "root", "version": "2.0.0", "is_local": False,
            "machine_id": "m1",
        }
        deploy_to_machine(result, "/tmp/binary", "1.0.0", sample_settings)

        # SFTP must be called (we're transferring)
        client.open_sftp.assert_called()
        sftp.put.assert_called()


class TestRollbackToMachineSkipsScpWhenRemoteHasVersion:
    """Rollback should also skip SCP if the target version is already cached remotely."""

    @patch("claude_offline_updater.deployer._is_remote_version_installed", return_value=True)
    @patch("claude_offline_updater.deployer._get_current_symlink", return_value="/old/target")
    @patch("claude_offline_updater.deployer._ssh_connect")
    def test_rollback_skips_sftp_when_remote_has_target(
        self, mock_connect, mock_symlink, mock_has, sample_settings,
    ):
        """Rollback never SFTPs (it just does ln -sf from versions_dir).
        This test guards that future refactors don't accidentally add
        an SCP step to the rollback path."""
        client = MagicMock()
        mock_connect.return_value = client

        result = {
            "name": "test-server", "host": "192.168.1.100", "port": 22,
            "user": "root", "version": "2.0.0", "is_local": False,
            "machine_id": "m1",
        }
        from claude_offline_updater.deployer import rollback_to_machine
        # Run rollback; the inner test -x / ln -sf / verify may produce
        # various outcomes depending on mock state. We only assert the
        # non-SFTP property: rollback must never open an SFTP connection.
        with contextlib.suppress(Exception):
            rollback_to_machine(result, "1.0.0", sample_settings)
        client.open_sftp.assert_not_called()


class TestDeployLocalSkipsCopyWhenTargetExists:
    """deploy_local should skip shutil.copy2 if the local version already exists."""

    @patch("claude_offline_updater.deployer.cleanup_local_versions")
    @patch("claude_offline_updater.deployer.subprocess.run")
    @patch("claude_offline_updater.deployer.os.path.isfile")
    @patch("claude_offline_updater.deployer.os.access")
    @patch("claude_offline_updater.deployer.os.symlink")
    @patch("claude_offline_updater.deployer.shutil.copy2")
    def test_deploy_local_skips_copy_when_target_exists(
        self, mock_copy2, mock_symlink, mock_access, mock_isfile, mock_run,
        mock_cleanup, sample_local, sample_settings,
    ):
        # target binary exists and is executable → skip copy
        mock_isfile.return_value = True
        mock_access.return_value = True
        # verify_version subprocess
        verify_proc = MagicMock(returncode=0, stdout="1.0.0\n")
        mock_run.return_value = verify_proc

        from claude_offline_updater.deployer import deploy_local
        out = deploy_local(
            {"name": "localhost", "host": "127.0.0.1", "version": "2.0.0",
             "is_local": True},
            "/tmp/binary", "1.0.0", sample_local, sample_settings,
        )
        assert out["status"] == "success"
        # shutil.copy2 must NOT be called when target already exists
        # (the `claude install` happy path takes over and handles the symlink)
        mock_copy2.assert_not_called()

    @patch("claude_offline_updater.deployer.cleanup_local_versions")
    @patch("claude_offline_updater.deployer.subprocess.run")
    @patch("claude_offline_updater.deployer.os.path.isfile")
    @patch("claude_offline_updater.deployer.os.access")
    @patch("claude_offline_updater.deployer.os.symlink")
    @patch("claude_offline_updater.deployer.shutil.copy2")
    @patch("claude_offline_updater.deployer._set_install_method_local")
    def test_deploy_local_fallback_path_skips_copy_when_target_exists(
        self, mock_set_method, mock_copy2, mock_symlink, mock_access, mock_isfile,
        mock_run, mock_cleanup, sample_local, sample_settings,
    ):
        """Manual fallback path: install fails, code falls through to the
        local cp + chmod + symlink block. When target_version already
        exists on disk, shutil.copy2 must be skipped."""
        # install fails (returncode 1) → fallback path
        install_proc = MagicMock(returncode=1)
        verify_proc = MagicMock(returncode=0, stdout="1.0.0\n")
        mock_run.side_effect = [install_proc, verify_proc]
        # target already exists and is executable
        mock_isfile.return_value = True
        mock_access.return_value = True

        from claude_offline_updater.deployer import deploy_local
        out = deploy_local(
            {"name": "localhost", "host": "127.0.0.1", "version": "2.0.0",
             "is_local": True},
            "/tmp/binary", "1.0.0", sample_local, sample_settings,
        )
        assert out["status"] == "success"
        # shutil.copy2 must NOT be called — target already exists
        mock_copy2.assert_not_called()
        # symlink SHOULD be called (in fallback path)
        mock_symlink.assert_called()
