import os

import pytest

from claude_offline_updater.cleaner import cleanup_local_versions
from claude_offline_updater.config import LocalConfig


@pytest.fixture
def local_with_dir(tmp_path):
    versions_dir = tmp_path / "versions"
    versions_dir.mkdir()
    return LocalConfig(
        enabled=True,
        versions_dir=str(versions_dir),
    ), versions_dir


class TestCleanupLocalVersions:
    def test_no_versions_dir_no_error(self, tmp_path):
        local = LocalConfig(
            enabled=True,
            versions_dir=str(tmp_path / "nonexistent"),
        )
        cleanup_local_versions(local, max_versions=3)

    def test_removes_zero_byte_files(self, local_with_dir):
        local, versions_dir = local_with_dir
        (versions_dir / "1.0.0").write_bytes(b"")
        (versions_dir / "2.0.0").write_bytes(b"\x00" * 100)
        os.chmod(versions_dir / "2.0.0", 0o755)
        cleanup_local_versions(local, max_versions=3)
        remaining = list(versions_dir.iterdir())
        assert len(remaining) == 1
        assert remaining[0].name == "2.0.0"

    def test_removes_non_executable_files(self, local_with_dir):
        local, versions_dir = local_with_dir
        (versions_dir / "1.0.0").write_bytes(b"\x00" * 100)
        os.chmod(versions_dir / "1.0.0", 0o644)
        (versions_dir / "2.0.0").write_bytes(b"\x00" * 100)
        os.chmod(versions_dir / "2.0.0", 0o755)
        cleanup_local_versions(local, max_versions=3)
        remaining = list(versions_dir.iterdir())
        assert len(remaining) == 1
        assert remaining[0].name == "2.0.0"

    def test_keeps_latest_n_versions(self, local_with_dir):
        local, versions_dir = local_with_dir
        for i, v in enumerate(["1.0.0", "2.0.0", "3.0.0", "4.0.0"]):
            p = versions_dir / v
            p.write_bytes(b"\x00" * 100)
            os.chmod(p, 0o755)
            mtime = 1000 + i
            os.utime(p, (mtime, mtime))
        cleanup_local_versions(local, max_versions=2)
        remaining = sorted(f.name for f in versions_dir.iterdir())
        assert remaining == ["3.0.0", "4.0.0"]

    def test_keeps_all_when_within_limit(self, local_with_dir):
        local, versions_dir = local_with_dir
        for v in ["1.0.0", "2.0.0"]:
            p = versions_dir / v
            p.write_bytes(b"\x00" * 100)
            os.chmod(p, 0o755)
        cleanup_local_versions(local, max_versions=5)
        assert len(list(versions_dir.iterdir())) == 2

    def test_empty_directory_no_error(self, local_with_dir):
        local, versions_dir = local_with_dir
        cleanup_local_versions(local, max_versions=3)
        assert len(list(versions_dir.iterdir())) == 0
