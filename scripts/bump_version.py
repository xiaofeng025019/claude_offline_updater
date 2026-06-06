#!/usr/bin/env python3
"""Bump version in pyproject.toml based on conventional commits or explicit level."""

import argparse
import re
import subprocess
import sys
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

LEVELS = ("patch", "minor", "major")


def read_version() -> str:
    text = PYPROJECT.read_text()
    m = re.search(r'^version\s*=\s*"(\d+\.\d+\.\d+)"', text, re.MULTILINE)
    if not m:
        print("ERROR: version not found in pyproject.toml", file=sys.stderr)
        sys.exit(1)
    return m.group(1)


def write_version(version: str):
    text = PYPROJECT.read_text()
    text = re.sub(
        r'^version\s*=\s*"\d+\.\d+\.\d+"',
        f'version = "{version}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    PYPROJECT.write_text(text)


def bump(version: str, level: str) -> str:
    major, minor, patch = (int(x) for x in version.split("."))
    if level == "major":
        return f"{major + 1}.0.0"
    elif level == "minor":
        return f"{major}.{minor + 1}.0"
    else:
        return f"{major}.{minor}.{patch + 1}"


def detect_level_from_commits(commits: list[str]) -> str | None:
    """Determine bump level from conventional commit messages.

    Rules:
      - feat! / BREAKING CHANGE → major
      - feat: → minor
      - fix: / perf: → patch
      - others → None (skip)
    """
    has_feat = False
    has_fix = False
    has_perf = False
    has_breaking = False

    for msg in commits:
        first_line = msg.split("\n", 1)[0]
        if re.match(r"^[a-z]+(\(.+\))?!:", first_line) or "BREAKING CHANGE" in msg:
            has_breaking = True
        if first_line.startswith("feat"):
            has_feat = True
        if first_line.startswith("fix"):
            has_fix = True
        if first_line.startswith("perf"):
            has_perf = True

    if has_breaking:
        return "major"
    if has_feat:
        return "minor"
    if has_fix or has_perf:
        return "patch"
    return None


def get_recent_commits(since_tag: str | None = None) -> list[str]:
    """Get commit messages since a given tag (or all if no tag)."""
    cmd = ["git", "log", "--format=%B---DELIMITER---"]
    if since_tag:
        cmd.insert(2, f"{since_tag}..HEAD")
    result = subprocess.run(cmd, capture_output=True, text=True)
    raw = result.stdout.strip()
    if not raw:
        return []
    return [m.strip() for m in raw.split("---DELIMITER---") if m.strip()]


def get_latest_tag() -> str | None:
    result = subprocess.run(
        ["git", "tag", "--sort=-v:refname", "--list", "v*"],
        capture_output=True, text=True,
    )
    tags = result.stdout.strip().splitlines()
    return tags[0] if tags else None


def main():
    parser = argparse.ArgumentParser(description="Bump version in pyproject.toml")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--level", choices=LEVELS, help="Explicit bump level")
    group.add_argument(
        "--from-commits", action="store_true",
        help="Auto-detect level from conventional commit messages since last tag",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print new version without modifying files",
    )
    args = parser.parse_args()

    current = read_version()

    if args.from_commits:
        tag = get_latest_tag()
        commits = get_recent_commits(tag)
        level = detect_level_from_commits(commits)
        if level is None:
            print(f"No feat/fix commits found since {tag or 'beginning'} — skipping bump")
            print(f"Current version: {current}")
            sys.exit(0)
        since = tag or "beginning"
        print(f"Detected bump level: {level} (from {len(commits)} commits since {since})")
    else:
        level = args.level

    new_version = bump(current, level)

    if args.dry_run:
        print(f"{current} → {new_version} (dry run)")
    else:
        write_version(new_version)
        print(new_version)


if __name__ == "__main__":
    main()
