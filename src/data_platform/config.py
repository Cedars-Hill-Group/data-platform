"""
Configuration loader for the data platform.

Reads ``config.yaml`` (gitignored) from the project root, or from an explicit
path supplied via the ``DATA_PLATFORM_CONFIG`` environment variable.

Usage::

    from data_platform.config import get_config

    cfg = get_config()
    kb_path = cfg.knowledge_base.path
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class KnowledgeBaseConfig(BaseModel):
    path: Path = Field(..., description="Root directory of the markdown Knowledge Base.")


class DatabaseConfig(BaseModel):
    url: str = Field("sqlite:///data_platform.db", description="SQLAlchemy connection string.")
    echo: bool = False
    pool_size: int = 5
    max_overflow: int = 10


class WarehouseConfig(BaseModel):
    type: str = Field("none", description="Warehouse backend type (bigquery|snowflake|redshift|none).")
    project: str | None = None
    dataset: str | None = None
    account: str | None = None
    user: str | None = None
    password: str | None = None
    warehouse: str | None = None
    database: str | None = None
    schema_name: str | None = Field(None, alias="schema")

    model_config = {"populate_by_name": True}


class ObjectStorageConfig(BaseModel):
    type: str = Field("none", description="Storage backend type (s3|gcs|azure|local|none).")
    bucket: str | None = None
    prefix: str = ""
    region: str | None = None
    root_path: Path | None = None


# ---------------------------------------------------------------------------
# Root config model
# ---------------------------------------------------------------------------


class DataPlatformConfig(BaseModel):
    knowledge_base: KnowledgeBaseConfig
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    warehouse: WarehouseConfig = Field(default_factory=lambda: WarehouseConfig(type="none"))
    object_storage: ObjectStorageConfig = Field(
        default_factory=lambda: ObjectStorageConfig(type="none")
    )


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

_DEFAULT_PATHS: tuple[str, ...] = (
    "config.yaml",
    "config.yml",
)


def _find_config_file() -> Path:
    """Locate the config file, checking the env var first then defaults."""
    env_path = os.environ.get("DATA_PLATFORM_CONFIG")
    if env_path:
        p = Path(env_path)
        if not p.exists():
            raise FileNotFoundError(
                f"Config file specified by DATA_PLATFORM_CONFIG not found: {p}"
            )
        return p

    # Walk up from CWD looking for config.yaml
    cwd = Path.cwd()
    for candidate in (cwd / name for name in _DEFAULT_PATHS):
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        "No config.yaml found. Copy config.yaml.example to config.yaml and fill in your values, "
        "or set the DATA_PLATFORM_CONFIG environment variable."
    )


@lru_cache(maxsize=1)
def get_config(config_path: str | None = None) -> DataPlatformConfig:
    """Load and cache the platform configuration.

    Parameters
    ----------
    config_path:
        Optional explicit path to the YAML config file.  When *None* the
        loader checks ``$DATA_PLATFORM_CONFIG`` then the standard defaults.

    Returns
    -------
    DataPlatformConfig
        Validated configuration object.
    """
    if config_path is not None:
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
    else:
        path = _find_config_file()

    with path.open() as fh:
        raw = yaml.safe_load(fh)

    return DataPlatformConfig.model_validate(raw)


def reset_config_cache() -> None:
    """Clear the cached configuration (useful in tests)."""
    get_config.cache_clear()
