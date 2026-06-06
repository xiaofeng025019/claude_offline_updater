"""Download + cache + SHA256 verification module"""

import hashlib
import shutil
import time
from pathlib import Path

import httpx
from packaging.version import Version

from .config import Settings
from .display import create_download_progress, error, info, success, warn
from .i18n import t


class DownloadError(Exception):
    """Error during download/verification"""
    pass


def _version_sort_key(filename: str) -> tuple:
    """Sort key using semantic version parsing, fallback to filename string"""
    parts = filename.split("-", 2)
    if len(parts) >= 2:
        try:
            return (0, Version(parts[1]))
        except Exception:
            pass
    return (1, filename)


def cache_dir(settings: Settings) -> Path:
    """Get local cache directory, create if not exists"""
    p = Path(settings.local_cache_dir).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _cache_path(settings: Settings, version: str) -> Path:
    """Get cache path for a specific version"""
    return cache_dir(settings) / f"claude-{version}-{settings.platform}"


def get_cached_binary(settings: Settings, version: str) -> Path | None:
    """Check if a specific version binary exists in local cache"""
    path = _cache_path(settings, version)
    if path.exists() and path.stat().st_size > 0:
        return path
    return None


def list_cache(settings: Settings) -> list[dict]:
    """List all versions in local cache"""
    cache = cache_dir(settings)
    results = []
    for f in sorted(cache.glob("claude-*"), key=lambda p: _version_sort_key(p.name), reverse=True):
        parts = f.name.split("-", 2)
        if len(parts) >= 3:
            ver = parts[1]
            plat = parts[2]
            size_mb = f.stat().st_size / (1024 * 1024)
            results.append({
                "version": ver,
                "platform": plat,
                "path": str(f),
                "size_mb": round(size_mb, 1),
            })
    return results


def clean_cache(settings: Settings, keep: int | None = None):
    """Clean local cache, keep only the latest N versions"""
    if keep is None:
        keep = settings.max_cache_versions
    entries = list_cache(settings)
    if len(entries) <= keep:
        return

    to_remove = entries[keep:]
    for entry in to_remove:
        Path(entry["path"]).unlink(missing_ok=True)
        info(t("cache_clean_entry",
               version=entry['version'],
               platform=entry['platform'],
               size_mb=entry['size_mb']))

    success(f"{t('cache_cleaned')} {keep} {t('cache_cleaned_delete')} {len(to_remove)}")


def check_network(settings: Settings) -> bool:
    """Check download server network connectivity"""
    try:
        resp = httpx.head(
            f"{settings.download_base}/latest",
            timeout=10, follow_redirects=True,
        )
        return resp.status_code < 500
    except Exception:
        return False


def get_latest_version(settings: Settings) -> str:
    """Query latest version number (with retries)"""
    info(t("querying_version"))

    url = f"{settings.download_base}/latest"

    for attempt in range(1, settings.max_retries + 1):
        try:
            # Try the GET directly. If the server is unreachable, the
            # GET will raise a connection error — no need for a separate
            # HEAD precheck (saves one HTTP round-trip per scan).
            resp = httpx.get(url, timeout=30, follow_redirects=True)
            if resp.status_code < 500:
                version = resp.text.strip()
                if version:
                    return version
            if attempt < settings.max_retries:
                warn(t("query_retrying", attempt=attempt, max_retries=settings.max_retries))
                time.sleep(2)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout):
            # Connection-level failure — surface as "network unreachable"
            if attempt == 1:
                warn(t("network_unreachable"))
            if attempt < settings.max_retries:
                warn(t("query_retrying", attempt=attempt, max_retries=settings.max_retries))
                time.sleep(2)
        except Exception:
            if attempt < settings.max_retries:
                warn(t("query_retrying", attempt=attempt, max_retries=settings.max_retries))
                time.sleep(2)

    error(f"{t('version_unavailable_retry')} {settings.max_retries} {t('version_times')}")
    raise DownloadError(t("version_unavailable"))


def download_binary(settings: Settings, version: str, output_path: str) -> str:
    """Download binary file (prefer local cache, download and cache on miss).

    Returns the path to a usable binary — either the cache path (cache hit,
    no copy performed) or `output_path` (cache miss, downloaded to that path).
    The returned path is suitable for verify_checksum and deployer.
    """
    cached = get_cached_binary(settings, version)
    if cached:
        size_mb = cached.stat().st_size / (1024 * 1024)
        success(f"{t('download_hit_cache')}: {cached.name} ({size_mb:.1f}MB)")
        # No copy: the cache IS the source of truth. The deployer will
        # read directly from the cache, saving 10-50 MB of disk I/O.
        return str(cached)

    url = f"{settings.download_base}/{version}/{settings.platform}/claude"
    info(f"{t('downloading')} Claude Code {version} ({t('download_cache_miss')}) ...")

    last_error = t("download_empty")
    for attempt in range(1, settings.max_retries + 1):
        is_last = attempt == settings.max_retries
        try:
            _download_with_progress(url, output_path, settings.download_timeout)
        except Exception as e:
            last_error = str(e)
            Path(output_path).unlink(missing_ok=True)
        else:
            if Path(output_path).stat().st_size > 0:
                size_mb = Path(output_path).stat().st_size / (1024 * 1024)
                success(f"{t('download_complete')}: {size_mb:.1f}MB")
                cache_target = _cache_path(settings, version)
                shutil.copy2(output_path, cache_target)
                info(f"{t('cached_to')}: {cache_target}")
                clean_cache(settings)
                return
            # Empty file with no exception
            last_error = t("download_empty")
            error(last_error)
            Path(output_path).unlink(missing_ok=True)

        if not is_last:
            warn(t("download_retrying", attempt=attempt, max_retries=settings.max_retries))
            time.sleep(3)
            continue

        # Final attempt failed
        error(
            f"{t('download_failed')}（"
            f"{t('version_unavailable_retry')} "
            f"{settings.max_retries} {t('version_times')}）: {last_error}"
        )
        raise DownloadError(last_error)


def _download_with_progress(url: str, output_path: str, timeout: int):
    """Stream download with progress bar"""
    with httpx.Client(timeout=timeout, follow_redirects=True) as client, \
         client.stream("GET", url) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))

            with create_download_progress() as progress:
                task = progress.add_task(t("downloading"), total=total or None)
                with open(output_path, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=8192):
                        f.write(chunk)
                        progress.update(task, advance=len(chunk))


def verify_checksum(settings: Settings, version: str, file_path: str):
    """SHA256 verification"""
    if not check_network(settings):
        warn(t("network_skip_verify"))
        return

    info(t("verifying_checksum"))
    manifest_url = f"{settings.download_base}/{version}/manifest.json"

    try:
        resp = httpx.get(manifest_url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        manifest = resp.json()
    except Exception:
        warn(t("checksum_skip"))
        return

    expected = None
    platforms = manifest.get("platforms", {})
    if settings.platform in platforms:
        expected = platforms[settings.platform].get("checksum")

    if not expected:
        warn(t("checksum_no_value"))
        return

    info(f"{t('checksum_expected')}: {expected[:16]}...")

    actual = _sha256_file(file_path)
    if expected != actual:
        error(t("checksum_fail"))
        error(f"{t('checksum_expected_lbl')}: {expected}")
        error(f"{t('checksum_actual_lbl')}: {actual}")
        cached = get_cached_binary(settings, version)
        if cached:
            cached.unlink()
            warn(f"{t('cache_corrupted')}: {cached.name}")
        raise DownloadError(t("checksum_fail"))

    success(t("checksum_ok"))


def _sha256_file(path: str) -> str:
    """Compute file SHA256"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
