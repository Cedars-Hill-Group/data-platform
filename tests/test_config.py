"""Tests for data_platform.config."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from data_platform.config import (
    DataPlatformConfig,
    DatabaseConfig,
    KnowledgeBaseConfig,
    ObjectStorageConfig,
    OutputConfig,
    WarehouseConfig,
    get_config,
    reset_config_cache,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    """Ensure config cache is cleared before and after each test."""
    reset_config_cache()
    yield
    reset_config_cache()


class TestConfigLoading:
    def test_load_from_explicit_path(self, config_file: Path, kb_root: Path):
        cfg = get_config(str(config_file))
        assert isinstance(cfg, DataPlatformConfig)
        assert cfg.knowledge_base.path == kb_root

    def test_database_defaults(self, config_file: Path):
        cfg = get_config(str(config_file))
        assert cfg.database.url == "sqlite:///:memory:"
        assert cfg.database.echo is False

    def test_warehouse_defaults(self, config_file: Path):
        cfg = get_config(str(config_file))
        assert cfg.warehouse.type == "none"

    def test_object_storage_defaults(self, config_file: Path):
        cfg = get_config(str(config_file))
        assert cfg.object_storage.type == "none"

    def test_output_defaults(self, config_file: Path):
        cfg = get_config(str(config_file))
        assert cfg.output.path == Path("output")

    def test_missing_config_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            get_config(str(tmp_path / "nonexistent.yaml"))

    def test_invalid_yaml_raises(self, tmp_path: Path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("knowledge_base: {path: /kb}\ndatabase: [not a mapping]")
        with pytest.raises(Exception):
            get_config(str(bad))

    def test_caching(self, config_file: Path):
        cfg1 = get_config(str(config_file))
        cfg2 = get_config(str(config_file))
        assert cfg1 is cfg2

    def test_reset_cache_allows_reload(self, tmp_path: Path, kb_root: Path):
        cfg_data = {
            "knowledge_base": {"path": str(kb_root)},
            "database": {"url": "sqlite:///first.db"},
            "warehouse": {"type": "none"},
            "object_storage": {"type": "none"},
        }
        p = tmp_path / "cfg.yaml"
        p.write_text(yaml.dump(cfg_data))
        cfg1 = get_config(str(p))
        assert "first.db" in cfg1.database.url

        reset_config_cache()
        cfg_data["database"]["url"] = "sqlite:///second.db"
        p.write_text(yaml.dump(cfg_data))
        cfg2 = get_config(str(p))
        assert "second.db" in cfg2.database.url


class TestConfigModels:
    def test_knowledge_base_config(self, tmp_path: Path):
        kb = KnowledgeBaseConfig(path=tmp_path)
        assert kb.path == tmp_path
        assert kb.companies_dir == "companies"
        assert kb.people_dir == "people"
        assert kb.projects_dir == "projects"

    def test_database_config_defaults(self):
        db = DatabaseConfig()
        assert db.url == "sqlite:///data_platform.db"
        assert db.pool_size == 5

    def test_warehouse_config_schema_alias(self):
        wh = WarehouseConfig(type="snowflake", **{"schema": "MY_SCHEMA"})
        assert wh.schema_name == "MY_SCHEMA"

    def test_object_storage_config(self):
        os_cfg = ObjectStorageConfig(type="s3", bucket="my-bucket", prefix="data/")
        assert os_cfg.type == "s3"
        assert os_cfg.bucket == "my-bucket"

    def test_output_config_defaults(self):
        output = OutputConfig()
        assert output.path == Path("output")
