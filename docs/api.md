# API Reference

Complete reference for all public modules and functions in `claude_offline_updater`.

## config.py -- Configuration Management

Handles YAML config loading, saving, and machine registry operations.

### `Config`

Top-level configuration container.

```python
@dataclass
class Config:
    settings: Settings
    local: LocalConfig
    machines: list[Machine]
    config_path: Path
```

| Method | Signature | Description |
|--------|-----------|-------------|
| `load` | `Config.load(path: Optional[str] = None, auto_create: bool = True) -> Config` | Class method. Loads config from a YAML file. Auto-creates default config if file not found (unless `auto_create=False`). Falls back to `CLAUDE_OFFLINE_CONFIG` env var, then `./config.yaml`, then `~/.config/claude-update/config.yaml`. |
| `create_default` | `Config.create_default(path: Optional[str] = None) -> Config` | Class method. Creates a default config file and returns the Config object. |
| `default_config_path` | `Config.default_config_path() -> Path` | Class method. Returns `~/.config/claude-update/config.yaml`. |
| `save` | `Config.save() -> None` | Atomically writes the current configuration back to the YAML file. |
| `find_machine` | `Config.find_machine(name: str) -> Optional[Machine]` | Looks up a machine by name. Returns the `Machine` object or `None`. |
| `add_machine` | `Config.add_machine(machine: Machine) -> None` | Appends a machine. Raises `ValueError` if a machine with the same name already exists. |
| `remove_machine` | `Config.remove_machine(name: str) -> bool` | Removes a machine by name. Returns `True` if found and removed, `False` otherwise. |

### `Machine`

Represents a single remote machine.

```python
@dataclass
class Machine:
    name: str
    host: str
    port: int = 22
    user: str = "root"
    tags: list[str] = field(default_factory=list)
```

| Property | Signature | Description |
|----------|-----------|-------------|
| `ssh_target` | `Machine.ssh_target -> str` | Returns the SSH target string in `user@host` format. |

### `LocalConfig`

Configuration for the local machine.

```python
@dataclass
class LocalConfig:
    enabled: bool = True
    claude_bin: str = "~/.local/bin/claude"
    versions_dir: str = "~/.local/share/claude/versions"
```

### `Settings`

Global settings with sensible defaults.

```python
@dataclass
class Settings:
    max_versions: int = 3
    remote_claude_bin: str = "~/.local/bin/claude"
    remote_versions_dir: str = "~/.local/share/claude/versions"
    remote_tmp_dir: str = "/tmp/claude-update"
    download_base: str = "https://downloads.claude.ai/claude-code-releases"
    platform: str = "linux-x64"
    local_cache_dir: str = "~/.cache/claude-update"
    connect_timeout: int = 10
    download_timeout: int = 300
    max_retries: int = 3
    max_workers: int = 5
    scp_bandwidth_limit: int = 0
    ssh_host_key_policy: str = "warn"
    lang: str = "en"
```

---

## downloader.py -- Download, Cache, and Checksum

Handles binary downloading with local cache, SHA256 verification, and network checks.

### `DownloadError`

```python
class DownloadError(Exception):
    """Error during download/verification"""
```

### Functions

| Function | Signature | Description |
|----------|-----------|-------------|
| `cache_dir` | `cache_dir(settings: Settings) -> Path` | Returns the local cache directory path, creating it if it does not exist. |
| `get_cached_binary` | `get_cached_binary(settings: Settings, version: str) -> Optional[Path]` | Checks whether a specific version exists in the local cache. Returns the `Path` if found, `None` otherwise. |
| `list_cache` | `list_cache(settings: Settings) -> list[dict]` | Lists all cached binaries. Each entry contains `version`, `platform`, `path`, and `size_mb`. Sorted by semantic version, newest first. |
| `clean_cache` | `clean_cache(settings: Settings, keep: int = 3) -> None` | Removes old cache entries, keeping only the `keep` most recent versions. |
| `check_network` | `check_network(settings: Settings) -> bool` | Tests connectivity to the download server via an HTTP HEAD request. Returns `True` if the server responds with a status below 500. |
| `get_latest_version` | `get_latest_version(settings: Settings) -> str` | Queries the latest Claude Code version number from the download server. Retries up to `max_retries` times. Raises `DownloadError` on failure. |
| `download_binary` | `download_binary(settings: Settings, version: str, output_path: str) -> None` | Downloads the binary for the given version. If the version is already cached, copies from cache instead. On cache miss, downloads with a progress bar, saves to cache, and triggers cache cleanup. Raises `DownloadError` after exhausting retries. |
| `verify_checksum` | `verify_checksum(settings: Settings, version: str, file_path: str) -> None` | Verifies the SHA256 checksum of a downloaded file against the official manifest. Skips verification gracefully if the network is unreachable or the manifest is unavailable. Raises `DownloadError` if the checksum does not match. |

---

## scanner.py -- Parallel Version Scanning

Scans Claude Code versions across local and remote machines in parallel.

| Function | Signature | Description |
|----------|-----------|-------------|
| `scan_local` | `scan_local(local: LocalConfig) -> dict` | Scans the local machine's Claude Code version by running `claude --version`. Returns a dict with `name`, `host`, `port`, `user`, `version`, `tags`, and `is_local`. |
| `scan_machine` | `scan_machine(machine: Machine, settings: Settings) -> dict` | Scans a single remote machine via SSH. Returns a dict with the same fields as `scan_local`, plus `is_local: False`. |
| `scan_all` | `scan_all(machines: list[Machine], settings: Settings, local: Optional[LocalConfig] = None) -> list[dict]` | Scans all machines in parallel using a `ThreadPoolExecutor`. Local machine is scanned first (if `local.enabled` is `True`). Results are sorted with localhost first, then remote machines in config order. Failed connections are captured gracefully. |

---

## deployer.py -- Deployment, Rollback, and Verification

Handles binary deployment to both local and remote machines with automatic rollback.

| Function | Signature | Description |
|----------|-----------|-------------|
| `deploy_local` | `deploy_local(result: dict, binary_path: str, target_version: str, local: LocalConfig, settings: Settings) -> dict` | Deploys to the local machine. Tries `claude install` first, falls back to manual symlink-based deployment. Verifies the installed version and rolls back the symlink on failure. Returns a result dict with `status` (`success`, `failed`, or `skipped`). |
| `deploy_to_machine` | `deploy_to_machine(result: dict, binary_path: str, target_version: str, settings: Settings) -> dict` | Deploys to a single remote machine via SSH/SFTP. Transfers the binary, attempts `claude install`, falls back to manual deployment. Verifies the version and rolls back on failure. Supports bandwidth-limited SCP transfers. |
| `deploy_all` | `deploy_all(selected: list[dict], binary_path: str, target_version: str, settings: Settings, local: Optional[LocalConfig] = None) -> list[dict]` | Deploys to all selected machines. Local machine is deployed first, then remote machines are deployed in parallel. Machines already at the target version are skipped. Results are sorted with localhost first. |

---

## cleaner.py -- Old Version Cleanup

Removes outdated or invalid Claude Code version binaries.

| Function | Signature | Description |
|----------|-----------|-------------|
| `cleanup_old_versions` | `cleanup_old_versions(client: paramiko.SSHClient, settings: Settings, label: str = "") -> None` | Cleans old versions on a remote machine via SSH. Removes zero-byte and non-executable files first, then keeps only the `max_versions` most recent binaries (sorted by mtime). |
| `cleanup_local_versions` | `cleanup_local_versions(local: LocalConfig, max_versions: int, label: str = "localhost") -> None` | Cleans old versions on the local machine. Same logic as the remote variant: removes invalid files, then keeps the `max_versions` most recent. |

---

## history.py -- Update History Tracking

Records and queries update history using a JSONL file (one JSON object per line).

| Function | Signature | Description |
|----------|-----------|-------------|
| `record_update` | `record_update(machine_name: str, machine_host: str, from_version: str, to_version: str, status: str, detail: str = "", duration_seconds: float = 0) -> None` | Appends a single update record to the history file with a timestamp. |
| `record_batch` | `record_batch(results: list[dict]) -> None` | Appends multiple update result records at once. All records in a batch share the same timestamp. |
| `get_history` | `get_history(machine: Optional[str] = None, limit: int = 50) -> list[dict]` | Reads and returns history records, optionally filtered by machine name. Results are sorted by timestamp descending, limited to `limit` entries. |

The history file is stored at `~/.local/share/claude-update/history.jsonl`.

---

## i18n.py -- Internationalization

Provides bilingual (Chinese/English) translation support.

| Function | Signature | Description |
|----------|-----------|-------------|
| `t` | `t(key: str, **kwargs) -> str` | Translation function. Returns the text for `key` in the current language. Supports `str.format()` keyword arguments. Falls back to the key itself if no translation is found. |
| `set_lang` | `set_lang(lang: str) -> None` | Sets the active language. Accepts `"zh"` or `"en"`. |
| `get_lang` | `get_lang() -> str` | Returns the currently active language code. Defaults to `"en"` unless overridden by `set_lang()` or the `CLAUDE_UPDATE_LANG` environment variable. |

The initial language is determined by the `CLAUDE_UPDATE_LANG` environment variable, defaulting to `"en"`.

---

## display.py -- Rich Console Output

Provides styled console output using the Rich library.

| Function / Object | Signature | Description |
|--------------------|-----------|-------------|
| `console` | `Console()` | Shared Rich `Console` instance for all output. |
| `info` | `info(msg: str) -> None` | Prints a blue `[INFO]` prefixed message. |
| `success` | `success(msg: str) -> None` | Prints a green `[OK]` prefixed message. |
| `warn` | `warn(msg: str) -> None` | Prints a yellow `[WARN]` prefixed message. |
| `error` | `error(msg: str) -> None` | Prints a red `[ERROR]` prefixed message. |
| `header` | `header(title: str) -> None` | Prints a bold Rich `Panel` with the given title. |
| `create_download_progress` | `create_download_progress() -> Progress` | Creates a Rich `Progress` instance with a bar, download size, transfer speed, and time remaining columns. |
| `show_scan_results` | `show_scan_results(results: list[dict], target_version: str) -> None` | Renders a Rich table of scan results with color-coded status (up to date, needs update, not installed, connection failed). |
| `show_update_results` | `show_update_results(results: list[dict]) -> None` | Renders a Rich table of update results with success/failure/skipped counts. |
| `show_history_table` | `show_history_table(records: list[dict]) -> None` | Renders a Rich table of update history records with timestamp, machine, version change, status, and duration columns. |
| `show_config_panels` | `show_config_panels(config: Config) -> None` | Renders structured Rich panels for settings, local config, and machine list. Changed values are highlighted in yellow. |

---

## selector.py -- Interactive Machine Selection

Provides an interactive multi-select interface for choosing which machines to update.

| Function | Signature | Description |
|----------|-----------|-------------|
| `select_machines` | `select_machines(scan_results: list[dict], target_version: str) -> list[dict]` | Displays a preview table of all machines, then presents a `questionary.checkbox` multi-select prompt. Machines that need updates are pre-selected; machines already at the target version are unselected. Returns the list of selected machine result dicts, or an empty list if the user cancels or goes back. |
