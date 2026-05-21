import pytest
import yaml

from claude_offline_updater.config import LocalConfig, Machine, Settings
from claude_offline_updater.i18n import set_lang


@pytest.fixture(autouse=True)
def set_english():
    set_lang("en")
    yield
    set_lang("en")


@pytest.fixture
def sample_settings():
    return Settings()


@pytest.fixture
def sample_local():
    return LocalConfig()


@pytest.fixture
def sample_machine():
    return Machine(name="test-server", host="192.168.1.100", port=22, user="root")


@pytest.fixture
def sample_config_yaml(tmp_path):
    data = {
        "settings": {
            "max_versions": 3,
            "platform": "linux-x64",
            "lang": "en",
        },
        "local": {
            "enabled": True,
            "claude_bin": "~/.local/bin/claude",
            "versions_dir": "~/.local/share/claude/versions",
        },
        "machines": [
            {"name": "server1", "host": "10.0.0.1", "port": 22, "user": "root"},
            {"name": "server2", "host": "10.0.0.2", "port": 2222, "user": "ubuntu"},
        ],
    }
    path = tmp_path / "config.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
    return path
