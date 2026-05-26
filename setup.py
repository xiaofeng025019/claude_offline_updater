"""Custom setup.py: writes git commit hash into _build_info.py at install time"""

import subprocess
from pathlib import Path

from setuptools import setup

PKG_DIR = Path(__file__).parent / "claude_offline_updater"


def _write_build_info():
    build_hash = ""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            build_hash = result.stdout.strip()
    except Exception:
        pass
    (PKG_DIR / "_build_info.py").write_text(f'build_hash = "{build_hash}"\n')


_write_build_info()
setup()
