# Contributing to Claude Code Offline Updater

Thank you for your interest in contributing to Claude Code Offline Updater. We appreciate your time and effort in helping improve this project. This document provides guidelines and instructions for contributing.

## Code of Conduct

We are committed to providing a welcoming and inclusive experience for everyone. Please be respectful and constructive in all interactions. Harassment, discrimination, and offensive behavior will not be tolerated.

## How to Contribute

### Reporting Bugs

If you find a bug, please open an issue using the [Bug Report template](https://github.com/xiaofeng025019/claude_offline_updater/issues/new?template=bug_report.yml). Include:

- A clear description of the problem
- Steps to reproduce the issue
- Expected vs. actual behavior
- Your operating system and Python version
- Any relevant logs or error messages

### Suggesting Features

We welcome feature suggestions. Please open an issue using the [Feature Request template](https://github.com/xiaofeng025019/claude_offline_updater/issues/new?template=feature_request.yml). Include:

- A clear description of the proposed feature
- The use case or problem it solves
- Any alternative solutions you have considered

### Pull Requests

1. Fork the repository
2. Create a new branch from `main` (see Branch Naming below)
3. Make your changes
4. Commit with a descriptive message (see Commit Messages below)
5. Push your branch to your fork
6. Open a Pull Request against the `main` branch
7. Ensure all tests pass and address any review feedback

## Development Setup

### Clone the Repository

```bash
git clone https://github.com/xiaofeng025019/claude_offline_updater.git
cd claude_offline_updater
```

### Create a Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows
```

### Install Dependencies

```bash
pip install -e ".[dev]"
```

> **Note:** Dev dependencies (ruff, pytest, pre-commit) are optional. The `[dev]` extra must be defined in `pyproject.toml` under `[project.optional-dependencies]` for this command to work. Without it, use `pip install -e .` and install dev tools separately.

### Initialize Configuration

```bash
claude-update config init
```

This creates a default config at `~/.config/claude-update/config.yaml` and prompts you to add your first remote machine. You can also run `claude-update config init --force` to overwrite an existing config.

### Run the Tool

```bash
claude-update
```

Or run as a module:

```bash
python -m claude_offline_updater
```

## Code Style

- Follow **PEP 8** conventions
- Use **type hints** with Python 3.10+ syntax (e.g., `list[dict]`, `str | None` instead of `List[Dict]`, `Optional[str]`)
- Write **docstrings** for all public functions and classes using **Google style**:

  ```python
  def update_package(name: str, version: str | None = None) -> bool:
      """Update a package to the specified version.

      Args:
          name: The package name.
          version: The target version, or None for latest.

      Returns:
          True if the update succeeded, False otherwise.
      """
  ```

- Maximum line length: **100 characters**
- Do not add unnecessary comments; let the code and docstrings speak for themselves

## Commit Messages

Use the [Conventional Commits](https://www.conventionalcommits.org/) format:

```
type(scope): description
```

Common types:

- `feat:` — A new feature
- `fix:` — A bug fix
- `docs:` — Documentation changes
- `style:` — Code style changes (formatting, no logic change)
- `refactor:` — Code refactoring
- `test:` — Adding or updating tests
- `chore:` — Build or tooling changes

Examples:

```
feat(update): add progress bar for download steps
fix(config): resolve missing key error on empty config
docs: update contributing guidelines
```

## Branch Naming

Use the following prefixes for branch names:

- `feature/` — New features (e.g., `feature/auto-rollback`)
- `bugfix/` — Bug fixes (e.g., `bugfix/ssh-timeout-handling`)
- `hotfix/` — Urgent fixes for production (e.g., `hotfix/crash-on-startup`)

## Testing

Run the full test suite before submitting a Pull Request:

```bash
pytest
```

Ensure all tests pass. If you are adding new functionality, include corresponding test cases.

## Translation

This project supports multiple languages through the `_T` dictionary in `i18n.py`. To add a new language:

1. Open `i18n.py` and locate the `_T` dictionary
2. Add a new key for the language code (e.g., `"fr"` for French)
3. Translate all string values into the target language
4. Ensure the dictionary structure matches existing entries exactly
5. Test the tool with the new language selected in your config

## License

By contributing to this project, you agree that your contributions will be licensed under the [MIT License](LICENSE).
