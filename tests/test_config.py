from pathlib import Path

import pytest
import yaml

from claude_offline_updater.config import Config, LocalConfig, Machine, Settings


class TestMachine:
    def test_default_port(self):
        m = Machine(name="s1", host="10.0.0.1")
        assert m.port == 22

    def test_default_tags(self):
        m = Machine(name="s1", host="10.0.0.1")
        assert m.tags == []

    def test_default_machine_id(self):
        m = Machine(name="s1", host="10.0.0.1")
        assert m.machine_id is None

    def test_machine_id_set(self):
        m = Machine(name="s1", host="10.0.0.1", machine_id="abc123")
        assert m.machine_id == "abc123"


class TestSettings:
    def test_defaults(self, sample_settings):
        s = sample_settings
        assert s.max_versions == 3
        assert s.max_cache_versions == 3
        assert s.remote_claude_bin == "~/.local/bin/claude"
        assert s.remote_versions_dir == "~/.local/share/claude/versions"
        assert s.remote_tmp_dir == "/tmp/claude-update"
        assert s.download_base == "https://downloads.claude.ai/claude-code-releases"
        assert s.platform == "linux-x64"
        assert s.local_cache_dir == "~/.cache/claude-update"
        assert s.connect_timeout == 10
        assert s.download_timeout == 300
        assert s.max_retries == 3
        assert s.max_workers == 5
        assert s.scp_bandwidth_limit == 0
        assert s.ssh_host_key_policy == "warn"
        assert s.lang == "en"


class TestLocalConfig:
    def test_defaults(self, sample_local):
        loc = sample_local
        assert loc.enabled is True
        assert loc.claude_bin == "~/.local/bin/claude"
        assert loc.versions_dir == "~/.local/share/claude/versions"


class TestConfigLoad:
    def test_load_valid_yaml(self, sample_config_yaml):
        config = Config.load(str(sample_config_yaml))
        assert config.settings.max_versions == 3
        assert config.settings.platform == "linux-x64"
        assert config.settings.lang == "en"
        assert config.local.enabled is True
        assert len(config.machines) == 2
        assert config.machines[0].name == "server1"
        assert config.machines[0].host == "10.0.0.1"
        assert config.machines[1].name == "server2"
        assert config.machines[1].port == 2222
        assert config.machines[1].user == "ubuntu"

    def test_load_missing_file_auto_creates(self, tmp_path):
        missing = tmp_path / "nonexistent.yaml"
        config = Config.load(str(missing))
        assert config.settings.max_versions == 3
        assert config.machines == []
        assert Path(str(missing)).exists()

    def test_load_missing_file_raises_when_no_auto(self, tmp_path):
        missing = tmp_path / "nonexistent.yaml"
        with pytest.raises(FileNotFoundError):
            Config.load(str(missing), auto_create=False)

    def test_load_env_override(self, sample_config_yaml, monkeypatch):
        monkeypatch.setenv("CLAUDE_OFFLINE_CONFIG", str(sample_config_yaml))
        config = Config.load()
        assert config.machines[0].name == "server1"

    def test_load_empty_machines(self, tmp_path):
        data = {
            "settings": {},
            "local": {},
            "machines": [],
        }
        path = tmp_path / "config.yaml"
        with open(path, "w") as f:
            yaml.dump(data, f)
        config = Config.load(str(path))
        assert config.machines == []

    def test_load_machines_missing_required_fields(self, tmp_path):
        data = {
            "settings": {},
            "local": {},
            "machines": [
                {"name": "valid", "host": "10.0.0.1"},
                {"name": "no_host"},
                {"host": "10.0.0.3"},
                {},
            ],
        }
        path = tmp_path / "config.yaml"
        with open(path, "w") as f:
            yaml.dump(data, f)
        config = Config.load(str(path))
        assert len(config.machines) == 1
        assert config.machines[0].name == "valid"

    def test_load_merges_defaults(self, tmp_path):
        data = {"settings": {"platform": "linux-arm64"}, "local": {}, "machines": []}
        path = tmp_path / "config.yaml"
        with open(path, "w") as f:
            yaml.dump(data, f)
        config = Config.load(str(path))
        assert config.settings.platform == "linux-arm64"
        assert config.settings.max_versions == 3
        assert config.settings.connect_timeout == 10

    def test_load_omitted_lang_defaults_to_en(self, tmp_path):
        data = {"settings": {"platform": "linux-x64"}, "local": {}, "machines": []}
        path = tmp_path / "config.yaml"
        with open(path, "w") as f:
            yaml.dump(data, f)
        config = Config.load(str(path))
        assert config.settings.lang == "en"


class TestConfigSave:
    def test_save_writes_correct_yaml(self, tmp_path):
        path = tmp_path / "config.yaml"
        settings = Settings(max_versions=5, platform="linux-arm64")
        local = LocalConfig(enabled=False)
        machines = [Machine(name="s1", host="10.0.0.1")]
        config = Config(settings=settings, local=local, machines=machines, config_path=path)
        config.save()

        with open(path) as f:
            data = yaml.safe_load(f)

        assert data["settings"]["max_versions"] == 5
        assert data["settings"]["platform"] == "linux-arm64"
        assert data["local"]["enabled"] is False
        assert len(data["machines"]) == 1
        assert data["machines"][0]["name"] == "s1"

    def test_save_roundtrip(self, sample_config_yaml):
        config = Config.load(str(sample_config_yaml))
        config.save()
        config2 = Config.load(str(sample_config_yaml))
        assert config2.settings.max_versions == config.settings.max_versions
        assert len(config2.machines) == len(config.machines)
        assert config2.machines[1].port == 2222

    def test_save_machine_id(self, tmp_path):
        path = tmp_path / "config.yaml"
        machines = [Machine(name="s1", host="10.0.0.1", machine_id="abc123")]
        config = Config(settings=Settings(), local=LocalConfig(), machines=machines,
                        config_path=path)
        config.save()
        config2 = Config.load(str(path))
        assert config2.machines[0].machine_id == "abc123"

    def test_save_machine_id_none_not_written(self, tmp_path):
        path = tmp_path / "config.yaml"
        machines = [Machine(name="s1", host="10.0.0.1")]
        config = Config(settings=Settings(), local=LocalConfig(), machines=machines,
                        config_path=path)
        config.save()
        with open(path) as f:
            data = yaml.safe_load(f)
        assert "machine_id" not in data["machines"][0]


class TestConfigOperations:
    def test_add_machine(self, tmp_path):
        config = Config(
            settings=Settings(), local=LocalConfig(), machines=[],
            config_path=tmp_path / "config.yaml",
        )
        m = Machine(name="new", host="10.0.0.5")
        config.add_machine(m)
        assert len(config.machines) == 1
        assert config.machines[0].name == "new"

    def test_add_machine_duplicate_raises(self, tmp_path):
        m1 = Machine(name="dup", host="10.0.0.1")
        m2 = Machine(name="dup", host="10.0.0.2")
        config = Config(
            settings=Settings(), local=LocalConfig(), machines=[m1],
            config_path=tmp_path / "config.yaml",
        )
        with pytest.raises(ValueError):
            config.add_machine(m2)

    def test_remove_machine_success(self, tmp_path):
        m = Machine(name="rm-me", host="10.0.0.1")
        config = Config(
            settings=Settings(), local=LocalConfig(), machines=[m],
            config_path=tmp_path / "config.yaml",
        )
        result = config.remove_machine("rm-me")
        assert result is True
        assert len(config.machines) == 0

    def test_remove_machine_failure(self, tmp_path):
        config = Config(
            settings=Settings(), local=LocalConfig(), machines=[],
            config_path=tmp_path / "config.yaml",
        )
        result = config.remove_machine("nonexistent")
        assert result is False

    def test_find_machine(self, tmp_path):
        m1 = Machine(name="alpha", host="10.0.0.1")
        m2 = Machine(name="beta", host="10.0.0.2")
        config = Config(
            settings=Settings(), local=LocalConfig(), machines=[m1, m2],
            config_path=tmp_path / "config.yaml",
        )
        found = config.find_machine("beta")
        assert found is m2
        assert found.host == "10.0.0.2"

    def test_find_machine_not_found(self, tmp_path):
        config = Config(
            settings=Settings(), local=LocalConfig(), machines=[],
            config_path=tmp_path / "config.yaml",
        )
        assert config.find_machine("ghost") is None

    def test_find_machine_by_id(self, tmp_path):
        m1 = Machine(name="alpha", host="10.0.0.1", machine_id="aaa111")
        m2 = Machine(name="beta", host="10.0.0.2", machine_id="bbb222")
        config = Config(
            settings=Settings(), local=LocalConfig(), machines=[m1, m2],
            config_path=tmp_path / "config.yaml",
        )
        found = config.find_machine_by_id("bbb222")
        assert found is m2

    def test_find_machine_by_id_not_found(self, tmp_path):
        config = Config(
            settings=Settings(), local=LocalConfig(), machines=[],
            config_path=tmp_path / "config.yaml",
        )
        assert config.find_machine_by_id("nonexistent") is None


class TestConfigCreateDefault:
    def test_creates_file(self, tmp_path):
        path = tmp_path / "new_config.yaml"
        config = Config.create_default(str(path))
        assert Path(str(path)).exists()
        assert config.machines == []
        assert config.settings.max_versions == 3

    def test_created_file_is_valid_yaml(self, tmp_path):
        path = tmp_path / "new_config.yaml"
        Config.create_default(str(path))
        with open(path) as f:
            data = yaml.safe_load(f)
        assert "settings" in data
        assert "local" in data
        assert "machines" in data

    def test_default_config_path(self):
        path = Config.default_config_path()
        assert str(path).endswith(".config/claude-update/config.yaml")
