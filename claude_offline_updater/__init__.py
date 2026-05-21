"""Claude Code Offline Updater"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("claude-offline-update")
except PackageNotFoundError:
    __version__ = "0.0.0"
