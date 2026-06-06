# CLAUDE.md — Project Guidance for Claude Code

> Project-specific rules and conventions. Read this when starting work in this repo.

## Project: claude-offline-update

A CLI tool to batch-update Claude Code across remote machines without direct
internet access. Uses SSH to deploy, downloads binaries via the configured
`download_base` URL.

- **Source:** `claude_offline_updater/*.py` (cli.py is the largest at ~1200 lines)
- **Tests:** `tests/test_*.py` — 199 tests, run with `pytest tests/ -q`
- **Linter:** Ruff — `python -m ruff check claude_offline_updater/ tests/`
- **Versioning:** Manual `Bump Version` workflow (Actions → run workflow →
  pick level). Auto-bump on every push was too noisy. Use conventional
  commits (feat → minor, fix → patch, BREAKING CHANGE → major) — the
  workflow can infer level from commits since the last tag, or you can
  pick explicitly.

## Workflow

- **Commit directly to main.** No PRs. Solo project.
- **Commit prefix determines version bump.** Use `feat:` / `fix:` / `chore:`
  per Conventional Commits.
- **Bumping version is manual** — go to GitHub Actions, run the
  `Bump Version` workflow, pick the level. The workflow commits
  `chore: bump version to X.Y.Z` and tags `vX.Y.Z`. Don't tag manually.
- **Push triggers CI.** Verify it passes before claiming done. Bump
  version separately when you're ready to publish.

## Code conventions

- **i18n is mandatory.** Every user-facing string goes through `t("key")` with
  both `zh` and `en` entries in `i18n.py`. Hardcoded English is a bug.
- **Path fields are validated at config load** via `_validate_path_chars`
  (whitelist: alphanum + `/._-~`). They are passed unquoted to the remote
  shell to preserve tilde expansion — do NOT wrap them in `shlex.quote`.
- **SSH commands are passed unquoted** for the same reason. Use
  `_is_safe_remote_path()` to validate any path derived from remote output
  (e.g., `readlink` result) before interpolating into a remote command.
- **Tests follow TDD.** Write failing test first, run it (confirm fail),
  implement, run again (confirm pass), commit.
- **No `print()` for user output.** Use the helpers in `display.py`
  (`info`, `success`, `warn`, `error`, `header`) and the Rich console.

## Pre-existing patterns

- `record_event(event_type, ...)` is the canonical event recorder. Don't
  bypass it with `_append_record` from feature code.
- `_auto_pin_on_rollback(result)` is the only place auto-pin is written.
  It catches all exceptions — pin write failure must not mask rollback.
- `Settings.pin_dedup_days: int = 30` controls the auto-pin dedup window.
  Unpin CLI never dedupes; pin CLI does, but accepts `--force`.
- `event_type` must be in `VALID_EVENT_TYPES` tuple in `history.py`.
  `record_event` validates required fields per event type — see the
  if/elif chain. Add a new event by: (1) add constant, (2) add to
  VALID_EVENT_TYPES, (3) extend `record_event` validation + field-set.

## Excluded from git

- `docs/superpowers/` — internal working docs (specs, plans). Untracked.
- Add to `.gitignore` if you see new such directories.

## When to ask vs. just do

- **Just do:** Fix obvious bugs, add tests, update i18n, refactor.
- **Ask first:** Change public CLI interface, change Settings schema,
  change default behavior of update/rollback, change version-bump rules.
