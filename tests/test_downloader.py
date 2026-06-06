import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from claude_offline_updater.config import Settings
from claude_offline_updater.downloader import (
    DownloadError,
    _cache_path,
    _sha256_file,
    cache_dir,
    clean_cache,
    download_binary,
    get_cached_binary,
    get_latest_version,
    list_cache,
    verify_checksum,
)


class TestCachePath:
    def test_returns_correct_path(self, sample_settings):
        result = _cache_path(sample_settings, "1.2.3")
        expected = Path(sample_settings.local_cache_dir).expanduser() / "claude-1.2.3-linux-x64"
        assert result == expected

    def test_different_platform(self):
        s = Settings(platform="linux-arm64")
        result = _cache_path(s, "2.0.0")
        assert result.name == "claude-2.0.0-linux-arm64"


class TestCacheDir:
    def test_creates_directory(self, tmp_path):
        cache = tmp_path / "new_cache"
        s = Settings(local_cache_dir=str(cache))
        result = cache_dir(s)
        assert result.exists()
        assert result.is_dir()

    def test_existing_directory(self, tmp_path):
        s = Settings(local_cache_dir=str(tmp_path))
        result = cache_dir(s)
        assert result == tmp_path


class TestGetCachedBinary:
    def test_returns_none_for_missing_file(self, tmp_path):
        s = Settings(local_cache_dir=str(tmp_path))
        assert get_cached_binary(s, "9.9.9") is None

    def test_returns_none_for_empty_file(self, tmp_path):
        s = Settings(local_cache_dir=str(tmp_path))
        path = _cache_path(s, "1.0.0")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        assert get_cached_binary(s, "1.0.0") is None

    def test_returns_path_for_existing_file(self, tmp_path):
        s = Settings(local_cache_dir=str(tmp_path))
        path = _cache_path(s, "1.0.0")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x00" * 100)
        result = get_cached_binary(s, "1.0.0")
        assert result == path


class TestListCache:
    def test_empty_directory(self, tmp_path):
        s = Settings(local_cache_dir=str(tmp_path))
        assert list_cache(s) == []

    def test_with_cached_files(self, tmp_path):
        s = Settings(local_cache_dir=str(tmp_path))
        (tmp_path / "claude-1.0.0-linux-x64").write_bytes(b"\x00" * (1024 * 1024))
        (tmp_path / "claude-2.0.0-linux-x64").write_bytes(b"\x00" * (2 * 1024 * 1024))
        results = list_cache(s)
        assert len(results) == 2
        assert results[0]["version"] == "2.0.0"
        assert results[1]["version"] == "1.0.0"
        assert results[0]["platform"] == "linux-x64"
        assert results[0]["size_mb"] == 2.0

    def test_ignores_non_matching_files(self, tmp_path):
        s = Settings(local_cache_dir=str(tmp_path))
        (tmp_path / "other-file.txt").write_bytes(b"data")
        (tmp_path / "claude-1.0.0-linux-x64").write_bytes(b"\x00" * 100)
        results = list_cache(s)
        assert len(results) == 1


class TestCleanCache:
    def test_keeps_latest_n_versions(self, tmp_path):
        s = Settings(local_cache_dir=str(tmp_path))
        for v in ["1.0.0", "2.0.0", "3.0.0", "4.0.0", "5.0.0"]:
            (tmp_path / f"claude-{v}-linux-x64").write_bytes(b"\x00" * 100)
        clean_cache(s, keep=2)
        remaining = list(tmp_path.glob("claude-*"))
        assert len(remaining) == 2
        names = sorted(f.name for f in remaining)
        assert "claude-4.0.0-linux-x64" in names
        assert "claude-5.0.0-linux-x64" in names

    def test_no_removal_when_within_limit(self, tmp_path):
        s = Settings(local_cache_dir=str(tmp_path))
        (tmp_path / "claude-1.0.0-linux-x64").write_bytes(b"\x00" * 100)
        (tmp_path / "claude-2.0.0-linux-x64").write_bytes(b"\x00" * 100)
        clean_cache(s, keep=5)
        assert len(list(tmp_path.glob("claude-*"))) == 2

    def test_uses_max_cache_versions_when_keep_is_none(self, tmp_path):
        s = Settings(local_cache_dir=str(tmp_path), max_cache_versions=2)
        for v in ["1.0.0", "2.0.0", "3.0.0", "4.0.0"]:
            (tmp_path / f"claude-{v}-linux-x64").write_bytes(b"\x00" * 100)
        clean_cache(s)
        remaining = list(tmp_path.glob("claude-*"))
        assert len(remaining) == 2
        names = sorted(f.name for f in remaining)
        assert "claude-3.0.0-linux-x64" in names
        assert "claude-4.0.0-linux-x64" in names


class TestSha256File:
    def test_produces_correct_hash(self, tmp_path):
        content = b"hello world"
        expected = hashlib.sha256(content).hexdigest()
        f = tmp_path / "testfile"
        f.write_bytes(content)
        assert _sha256_file(str(f)) == expected

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty"
        f.write_bytes(b"")
        expected = hashlib.sha256(b"").hexdigest()
        assert _sha256_file(str(f)) == expected


class TestDownloadError:
    def test_is_exception(self):
        assert issubclass(DownloadError, Exception)

    def test_message(self):
        e = DownloadError("test error")
        assert str(e) == "test error"


class TestGetLatestVersion:
    @patch("claude_offline_updater.downloader.httpx.get")
    def test_network_unreachable_raises(self, mock_get, sample_settings):
        """Connection-level failure must surface as DownloadError."""
        import httpx
        mock_get.side_effect = httpx.ConnectError("connection refused")
        with pytest.raises(DownloadError):
            get_latest_version(sample_settings)

    @patch("claude_offline_updater.downloader.httpx.get")
    def test_returns_version_on_success(self, mock_get, sample_settings):
        mock_resp = MagicMock()
        mock_resp.text = "1.5.0"
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp
        result = get_latest_version(sample_settings)
        assert result == "1.5.0"

    @patch("claude_offline_updater.downloader.httpx.get")
    def test_does_not_call_check_network_precheck(self, mock_get, sample_settings):
        """get_latest_version must NOT issue a separate HEAD precheck —
        the GET is the network probe and the data fetch in one round-trip."""
        from claude_offline_updater import downloader
        with patch.object(downloader, "check_network") as mock_check:
            mock_get.return_value = MagicMock(text="1.0.0", status_code=200)
            get_latest_version(sample_settings)
            mock_check.assert_not_called()

    @patch("claude_offline_updater.downloader.check_network", return_value=True)
    @patch("claude_offline_updater.downloader.httpx.get", side_effect=Exception("fail"))
    @patch("claude_offline_updater.downloader.time.sleep")
    def test_retries_then_raises(self, mock_sleep, mock_get, mock_net):
        s = Settings(max_retries=2)
        with pytest.raises(DownloadError):
            get_latest_version(s)
        assert mock_get.call_count == 2


class TestDownloadBinary:
    @patch("claude_offline_updater.downloader.shutil.copy2")
    @patch("claude_offline_updater.downloader.get_cached_binary")
    def test_cache_hit_skips_copy_uses_cache_path_directly(
        self, mock_cached, mock_copy, tmp_path, sample_settings,
    ):
        """When binary is in local cache, download_binary must NOT copy
        it to output_path — it returns the cache path so deployer can
        read the cached file directly. Saves a 10-50 MB local copy."""
        cached_file = tmp_path / "cached_binary"
        cached_file.write_bytes(b"\x00" * 200)
        mock_cached.return_value = cached_file

        output = str(tmp_path / "output")
        download_binary(sample_settings, "1.0.0", output)

        mock_cached.assert_called_once_with(sample_settings, "1.0.0")
        # No copy — the cache is the source of truth
        mock_copy.assert_not_called()
        # output_path is not used; the cache path is the real path
        assert not Path(output).exists()


class TestVerifyChecksum:
    @patch("claude_offline_updater.downloader.check_network", return_value=False)
    def test_network_unreachable_skips(self, mock_net, sample_settings, tmp_path):
        f = tmp_path / "binary"
        f.write_bytes(b"data")
        verify_checksum(sample_settings, "1.0.0", str(f))
        mock_net.assert_called_once()
