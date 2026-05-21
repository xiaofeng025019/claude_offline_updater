# Claude Code Offline Updater

[![Python Version](https://img.shields.io/badge/python-%3E%3D3.10-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub Release](https://img.shields.io/github/v/release/xiaofeng025019/claude_offline_updater?include_prereleases)](https://github.com/xiaofeng025019/claude_offline_updater/releases)

A CLI tool for batch-updating [Claude Code](https://docs.anthropic.com/en/docs/claude-code) across multiple remote machines that can't directly access the internet.

## Why?

In many environments (internal clusters, air-gapped servers, firewalled networks), remote machines cannot reach `downloads.claude.ai`. This tool solves that by:

1. **Downloading** the latest Claude Code binary locally (where internet is available)
2. **Caching** it locally for reuse
3. **SCP transferring** and **installing** it on remote machines via SSH
4. **Verifying** the installed version and **rolling back** on failure

## Features

- Multi-machine parallel scanning and deployment
- Interactive TUI with Rich panels and questionary selection
- Local binary cache -- download once, deploy many times
- SHA256 checksum verification against official manifest
- Automatic rollback on deployment failure
- Old version cleanup (keep latest N versions)
- Bandwidth-limited SCP transfers
- Local machine update support
- Bilingual UI (Chinese / English)
- Update history tracking (JSONL-based, zero external DB dependencies)

## Quick Start

### Install

```bash
pip install claude-offline-update
```

For development:

```bash
pip install -e ".[dev]"
```

### Configure

The tool auto-creates a default config on first run. To set up interactively:

```bash
# Interactive setup wizard (recommended)
claude-update config init

# Add machines after initial setup
claude-update config add-machine -n server1 -h 192.168.1.100

# View current config
claude-update config show
```

For advanced configuration, see [config.yaml.example](config.yaml.example) for all available settings.

### Run

```bash
# Interactive mode (recommended)
claude-update

# Or use subcommands
claude-update scan                    # Scan all machines
claude-update update --all            # Update all machines
claude-update update -m server1       # Update specific machines
claude-update update --dry-run        # Preview only
claude-update update -v 2.1.100      # Target a specific version
claude-update history                 # View update history
claude-update cache list              # List local cache
claude-update config show             # Show structured config
```

## Usage

### Interactive Mode

Run `claude-update` without arguments to enter the interactive menu:

```
+-------------------------------+
|  Claude Code Offline Updater  |
+-------------------------------+

  Scan machine versions
> Update Claude version
  View update history
  View/manage config
  Manage local cache
  Quit
```

The update flow: **Scan -> Select -> Download -> Deploy -> Verify**

### CLI Subcommands

**Top-level flags:**

| Flag | Description |
|------|-------------|
| `--config` / `-c` | Specify config file path |
| `--lang` / `-l` | Set UI language (zh/en) |

**Subcommands:**

| Command | Description |
|---------|-------------|
| `claude-update scan` | Scan all machines and display version status |
| `claude-update update --all` | Update all machines without prompting |
| `claude-update update -m srv1,srv2` | Update specific machines by name |
| `claude-update update -v 2.1.100` | Target a specific version instead of latest |
| `claude-update update --dry-run` | Preview what would be updated, no changes |
| `claude-update update --no-local` | Skip the local machine during update |
| `claude-update history` | View update history (all machines) |
| `claude-update history -m server1` | Filter history by machine name |
| `claude-update history -n 20` | Limit number of history records |
| `claude-update cache list` | List all cached binaries |
| `claude-update cache clean` | Clean old cache, keep latest 3 |
| `claude-update cache clean --keep N` | Clean old cache, keep latest N versions |
| `claude-update cache clean --all` | Clear entire cache |
| `claude-update config init` | Initialize config file (interactive) |
| `claude-update config show` | Structured view of all settings |
| `claude-update config add-machine` | Add a remote machine |
| `claude-update config rm-machine <name>` | Remove a remote machine |

### Config Management

Interactive config menu also supports editing global settings, local settings, and machine details.

### Language Switching

```bash
# Via CLI flag
claude-update --lang en scan

# Via config file
# settings.lang: en

# Via environment variable
CLAUDE_UPDATE_LANG=en claude-update scan
```

## API Documentation

The project is organized into focused modules:

| Module | Description |
|--------|-------------|
| `config.py` | YAML config loading, saving, and machine registry |
| `downloader.py` | Binary download with local cache and SHA256 verification |
| `scanner.py` | Parallel version scanning across local and remote machines |
| `deployer.py` | Deployment with automatic rollback and verification |
| `cleaner.py` | Old version cleanup (local and remote) |
| `history.py` | JSONL-based update history tracking |
| `i18n.py` | Bilingual translation support (Chinese/English) |
| `display.py` | Rich console output and table rendering |
| `selector.py` | Interactive machine selection UI |

For detailed function signatures and usage, see [docs/api.md](docs/api.md).

## Configuration

| Key | Default | Description |
|-----|---------|-------------|
| `max_versions` | 3 | Max versions to keep per machine |
| `platform` | linux-x64 | Binary platform: linux-x64, linux-arm64, darwin-arm64 |
| `lang` | en | UI language: en or zh |
| `connect_timeout` | 10 | SSH connect timeout (seconds) |
| `download_timeout` | 300 | Download timeout (seconds) |
| `max_retries` | 3 | Network operation retries |
| `max_workers` | 5 | Max parallel SSH connections |
| `scp_bandwidth_limit` | 0 | SCP bandwidth limit in KB/s (0 = unlimited) |
| `local_cache_dir` | ~/.cache/claude-update | Local binary cache directory |
| `remote_claude_bin` | ~/.local/bin/claude | Claude binary path on remote machines |
| `remote_versions_dir` | ~/.local/share/claude/versions | Versions directory on remote machines |
| `remote_tmp_dir` | /tmp/claude-update | Temporary directory on remote machines |
| `download_base` | https://downloads.claude.ai/claude-code-releases | Base URL for downloading binaries |
| `ssh_host_key_policy` | warn | SSH host key policy (auto/warn/reject) |

You can also specify the config file path via the `CLAUDE_OFFLINE_CONFIG` environment variable:

```bash
export CLAUDE_OFFLINE_CONFIG=/path/to/config.yaml
claude-update scan
```

## How It Works

### Deployment Flow

```
+---------------+    SCP     +----------------+
|  Local (you)  | --------> | Remote Server  |
|               |            |                |
| 1. Download   |            | 3. Install     |
|    binary     |            |    (or manual) |
| 2. Verify     |            | 4. Verify      |
|    checksum   |            |    version     |
|               |            | 5. Cleanup     |
+---------------+            +----------------+
```

1. **Download** -- Fetches from `downloads.claude.ai`, caches locally at `~/.cache/claude-update/`
2. **Transfer** -- SCP the binary to `/tmp/claude-update/claude` on each remote machine
3. **Install** -- Tries official `claude install` first; falls back to manual deploy (copy to versions dir + create symlink)
4. **Verify** -- Runs `claude --version` to confirm the installed version matches
5. **Rollback** -- If verification fails, restores the previous symlink
6. **Cleanup** -- Removes old/invalid versions beyond `max_versions`

### Version Management

Claude Code stores versions as individual binaries:

```
~/.local/share/claude/versions/
|-- 2.1.100
|-- 2.1.135
+-- 2.1.145          <- latest

~/.local/bin/claude -> ~/.local/share/claude/versions/2.1.145  (symlink)
```

This tool follows the same pattern -- switching versions is just updating the symlink.

## FAQ

### How do I set up SSH key-based authentication?

Generate an SSH key pair on the machine running this tool and copy the public key to each remote machine:

```bash
# Generate a key (if you don't have one)
ssh-keygen -t ed25519

# Copy the public key to each remote machine
ssh-copy-id root@192.168.1.100
ssh-copy-id root@192.168.1.101
```

After this, SSH and SFTP connections from this tool will not require a password. Key-based auth is strongly recommended for batch operations.

### What if the download server is unreachable?

If `downloads.claude.ai` is unreachable from your machine, you have two options:

1. **Use a cached binary**: If you have previously downloaded a version, it will be served from the local cache at `~/.cache/claude-update/`. Use `claude-update update -v <version>` to target a cached version.
2. **Manual placement**: Download the binary on another machine with internet access, then place it in the cache directory manually: `~/.cache/claude-update/claude-<version>-<platform>`.

You can verify connectivity with `claude-update scan`, which will warn you if the server is unreachable.

### How do I deploy to macOS machines?

Set the `platform` setting to `darwin-arm64` in your `config.yaml`:

```yaml
settings:
  platform: darwin-arm64
```

Note that all machines in a single config share the same platform setting. If you need to manage both Linux and macOS machines, use separate config files and invoke the tool with `--config`:

```bash
claude-update --config config-linux.yaml update --all
claude-update --config config-mac.yaml update --all
```

### How do I limit SCP bandwidth?

Set the `scp_bandwidth_limit` option in your `config.yaml`. The value is in KB/s:

```yaml
settings:
  scp_bandwidth_limit: 1024    # Limit to 1 MB/s
```

A value of `0` (the default) means unlimited bandwidth. When a limit is set, the tool uses the `scp` command-line tool with the `-l` flag instead of SFTP for the transfer.

### How do I rollback to a previous version?

This tool automatically rolls back on deployment failure. To manually switch to a previous version:

1. List the cached versions: `claude-update cache list`
2. Deploy a specific version: `claude-update update -v 2.1.100 -m server1`

Alternatively, you can manually update the symlink on any machine:

```bash
ln -sf ~/.local/share/claude/versions/2.1.100 ~/.local/bin/claude
```

### How do I add the tool to my system PATH?

If you installed with `pip install claude-offline-update`, the `claude-update` command should already be on your PATH. If not:

1. Find your Python user bin directory:
   ```bash
   python -m site --user-base
   ```
   The scripts directory is `<user-base>/bin`.

2. Add it to your shell profile (`~/.bashrc` or `~/.zshrc`):
   ```bash
   export PATH="$(python -m site --user-base)/bin:$PATH"
   ```

3. Reload your shell:
   ```bash
   source ~/.bashrc
   ```

For remote machines, the tool automatically ensures `~/.local/bin` is in PATH by appending it to `~/.bashrc` if missing.

## Requirements

- Python >= 3.10
- SSH access to remote machines (key-based auth recommended)
- Internet access from the machine running this tool (for downloads)

### Python Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| click | >= 8.0 | CLI framework |
| rich | >= 13.0 | Terminal formatting and progress bars |
| questionary | >= 2.0 | Interactive prompts |
| paramiko | >= 3.0, < 4.0 | SSH/SFTP connections |
| httpx | >= 0.24 | HTTP downloads |
| pyyaml | >= 6.0 | Config file parsing |
| packaging | >= 23.0 | Semantic version parsing |

## Project Structure

```
claude-offline/
|-- claude_offline_updater/      # Python package
|   |-- __init__.py              # Package metadata
|   |-- __main__.py              # Entry point for python -m
|   |-- cli.py                   # Click CLI + interactive menus
|   |-- config.py                # YAML config loading/saving
|   |-- scanner.py               # Parallel SSH version scanning
|   |-- downloader.py            # Download + cache + SHA256
|   |-- deployer.py              # SCP + install + rollback
|   |-- cleaner.py               # Old version cleanup
|   |-- display.py               # Rich tables/panels
|   |-- selector.py              # Interactive machine selection
|   |-- history.py               # JSONL update history
|   +-- i18n.py                  # Chinese/English translations
|-- tests/                       # Unit tests
|-- docs/
|   +-- api.md                   # API reference
|-- .github/
|   |-- workflows/
|   |   +-- ci.yml               # CI pipeline
|   +-- ISSUE_TEMPLATE/          # Bug report & feature request
|-- config.yaml.example          # Config template
+-- pyproject.toml               # Package config & dependencies
```

## Data Paths

This project follows the [XDG Base Directory Specification](https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html).

| Data | Default Path | Override |
|------|-------------|----------|
| Config | `~/.config/claude-update/` (XDG_CONFIG_HOME) | `$XDG_CONFIG_HOME`, `--config` flag, or `./config.yaml` |
| Data | `~/.local/share/claude-update/` (XDG_DATA_HOME) | `history.jsonl` |
| Cache | `~/.cache/claude-update/` (XDG_CACHE_HOME) | `local_cache_dir` setting |

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to submit issues, feature requests, and pull requests.

## License

This project is licensed under the [MIT License](LICENSE).
