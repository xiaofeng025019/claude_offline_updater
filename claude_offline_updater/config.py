"""YAML configuration loading and management"""

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .i18n import t

DEFAULTS = {
    "max_versions": 3,
    "remote_claude_bin": "~/.local/bin/claude",
    "remote_versions_dir": "~/.local/share/claude/versions",
    "remote_tmp_dir": "/tmp/claude-update",
    "download_base": "https://downloads.claude.ai/claude-code-releases",
    "platform": "linux-x64",
    "local_cache_dir": "~/.cache/claude-update",
    "connect_timeout": 10,
    "download_timeout": 300,
    "max_retries": 3,
    "max_workers": 5,
    "scp_bandwidth_limit": 0,
    "ssh_host_key_policy": "warn",
    "lang": "en",
}

_PATH_FIELDS = {
    "remote_claude_bin", "remote_versions_dir", "local_cache_dir",
    "claude_bin", "versions_dir",
}


def _shorten_path(path: str) -> str:
    """Replace home directory prefix with ~ for display/storage"""
    home = str(Path.home())
    if path.startswith(home + "/"):
        return "~" + path[len(home):]
    if path == home:
        return "~"
    return path


@dataclass
class Machine:
    name: str
    host: str
    port: int = 22
    user: str = "root"
    tags: list[str] = field(default_factory=list)


@dataclass
class LocalConfig:
    enabled: bool = True
    claude_bin: str = "~/.local/bin/claude"
    versions_dir: str = "~/.local/share/claude/versions"


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


@dataclass
class Config:
    settings: Settings
    local: LocalConfig
    machines: list[Machine]
    config_path: Path

    @classmethod
    def default_config_path(cls) -> Path:
        """Get the default config file path"""
        return Path.home() / ".config" / "claude-update" / "config.yaml"

    @classmethod
    def create_default(cls, path: str | None = None) -> "Config":
        """Create a default config file and return the Config object"""
        if path is None:
            path = os.environ.get("CLAUDE_OFFLINE_CONFIG")
            if not path:
                local_config = Path.cwd() / "config.yaml"
                if local_config.exists():
                    path = str(local_config)
                else:
                    path = str(cls.default_config_path())

        config_path = Path(path)
        config = cls(
            settings=Settings(),
            local=LocalConfig(),
            machines=[],
            config_path=config_path,
        )
        config.save()
        return config

    @classmethod
    def load(cls, path: str | None = None, auto_create: bool = True) -> "Config":
        """Load config file; auto-creates default if not found (unless auto_create=False)"""
        if path is None:
            path = os.environ.get("CLAUDE_OFFLINE_CONFIG")
            if not path:
                local_config = Path.cwd() / "config.yaml"
                if local_config.exists():
                    path = str(local_config)
                else:
                    path = str(cls.default_config_path())

        config_path = Path(path)
        if not config_path.exists():
            if auto_create:
                return cls.create_default(path)
            default_path = cls.default_config_path()
            raise FileNotFoundError(
                f"{t('config_not_found')}: {config_path}\n"
                f"{t('config_default_path')}: {default_path}\n"
                f"{t('config_init_hint')}"
            )

        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        # Parse settings
        raw_settings = data.get("settings", {})
        merged = {**DEFAULTS, **raw_settings}
        settings = Settings(**{k: v for k, v in merged.items()
                               if k in Settings.__dataclass_fields__})

        # Parse local config
        raw_local = data.get("local", {})
        local = LocalConfig(
            enabled=raw_local.get("enabled", True),
            claude_bin=raw_local.get("claude_bin", "~/.local/bin/claude"),
            versions_dir=raw_local.get("versions_dir", "~/.local/share/claude/versions"),
        )

        # Parse machines
        machines = []
        for m in data.get("machines", []):
            if not m.get("name") or not m.get("host"):
                continue
            machines.append(Machine(
                name=m["name"],
                host=m["host"],
                port=m.get("port", 22),
                user=m.get("user", "root"),
                tags=m.get("tags", []),
            ))

        return cls(settings=settings, local=local, machines=machines, config_path=config_path)

    def save(self):
        """Write current configuration back to file"""
        data = {
            "settings": {
                "max_versions": self.settings.max_versions,
                "remote_claude_bin": _shorten_path(self.settings.remote_claude_bin),
                "remote_versions_dir": _shorten_path(self.settings.remote_versions_dir),
                "remote_tmp_dir": self.settings.remote_tmp_dir,
                "download_base": self.settings.download_base,
                "platform": self.settings.platform,
                "local_cache_dir": _shorten_path(self.settings.local_cache_dir),
                "connect_timeout": self.settings.connect_timeout,
                "download_timeout": self.settings.download_timeout,
                "max_retries": self.settings.max_retries,
                "max_workers": self.settings.max_workers,
                "scp_bandwidth_limit": self.settings.scp_bandwidth_limit,
                "ssh_host_key_policy": self.settings.ssh_host_key_policy,
                "lang": self.settings.lang,
            },
            "local": {
                "enabled": self.local.enabled,
                "claude_bin": _shorten_path(self.local.claude_bin),
                "versions_dir": _shorten_path(self.local.versions_dir),
            },
            "machines": [
                {
                    "name": m.name,
                    "host": m.host,
                    "port": m.port,
                    "user": m.user,
                    **({"tags": m.tags} if m.tags else {}),
                }
                for m in self.machines
            ],
        }
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", suffix=".yaml",
            dir=self.config_path.parent, delete=False,
        ) as tmp:
            yaml.dump(data, tmp, default_flow_style=False, allow_unicode=True,
                      sort_keys=False)
            tmp_path = tmp.name
        os.replace(tmp_path, self.config_path)

    def find_machine(self, name: str) -> Machine | None:
        """Find machine by name"""
        for m in self.machines:
            if m.name == name:
                return m
        return None

    def add_machine(self, machine: Machine):
        """Add machine (name must be unique)"""
        if self.find_machine(machine.name):
            raise ValueError(f"{t('machine_exists')} '{machine.name}' {t('machine_exists_suffix')}")
        self.machines.append(machine)

    def remove_machine(self, name: str) -> bool:
        """Remove machine, returns whether successful"""
        for i, m in enumerate(self.machines):
            if m.name == name:
                self.machines.pop(i)
                return True
        return False
