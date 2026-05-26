"""Claude Code Offline Updater"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("claude-offline-update")
except PackageNotFoundError:
    __version__ = "0.0.0"


def _get_build_hash() -> str:
    """Read build-time git hash from _build_info.py, empty if not available"""
    try:
        from ._build_info import build_hash
        return build_hash
    except ImportError:
        return ""


def get_version_display() -> str:
    """Return version string like 'v1.1.0' or 'v1.1.0+abc1234'"""
    v = f"v{__version__}"
    h = _get_build_hash()
    if h:
        v += f"+{h}"
    return v
