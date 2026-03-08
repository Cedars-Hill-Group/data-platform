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

from data_platform.log import configure_logging, get_logger

_logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class KnowledgeBaseConfig(BaseModel):
    path: Path = Field(..., description="Root directory of the markdown Knowledge Base.")
    people_folder: str = Field("people", description="Sub-folder name for person documents.")
    companies_folder: str = Field("companies", description="Sub-folder name for company documents.")
    projects_folder: str = Field("projects", description="Sub-folder name for project documents.")

    @property
    def folder_map(self) -> dict[str, str]:
        """Return a mapping from canonical type name to folder name.

        Example::

            {"person": "people", "company": "companies", "project": "projects"}
        """
        return {
            "person": self.people_folder,
            "company": self.companies_folder,
            "project": self.projects_folder,
        }
    companies_dir: str = Field("companies", description="Sub-directory name for company files.")
    people_dir: str = Field("people", description="Sub-directory name for person files.")
    projects_dir: str = Field("projects", description="Sub-directory name for project files.")


class OutputConfig(BaseModel):
    path: Path = Field(
        Path("output"),
        description="Output directory for machine-readable artifacts (e.g. properties.json).",
    )


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


class LoggingConfig(BaseModel):
    """Logging configuration for the data platform.

    Maps to the optional ``logging:`` section in ``config.yaml``.
    """

    level: str = Field(
        "INFO",
        description="Minimum log level (DEBUG|INFO|WARNING|ERROR|CRITICAL).",
    )
    json_logs: bool = Field(
        False,
        description="Emit log records as single-line JSON when True.",
    )
    log_file: str | None = Field(
        None,
        description="Optional path to a log file (in addition to stdout).",
    )


# ---------------------------------------------------------------------------
# Root config model
# ---------------------------------------------------------------------------


class DataPlatformConfig(BaseModel):
    knowledge_base: KnowledgeBaseConfig
    output: OutputConfig = Field(default_factory=OutputConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    warehouse: WarehouseConfig = Field(default_factory=lambda: WarehouseConfig(type="none"))
    object_storage: ObjectStorageConfig = Field(
        default_factory=lambda: ObjectStorageConfig(type="none")
    )
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


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

    _logger.debug("Loading configuration from %s", path)

    with path.open() as fh:
        raw = yaml.safe_load(fh)

    config = DataPlatformConfig.model_validate(raw)

    # Auto-configure logging from the loaded config so callers don't have to
    # call configure_logging() manually.
    configure_logging(
        level=config.logging.level,
        json_logs=config.logging.json_logs,
        log_file=config.logging.log_file,
    )

    _logger.info(
        "Configuration loaded from %s (db=%s, warehouse=%s, storage=%s, log_level=%s)",
        path,
        config.database.url.split("://")[0],   # log scheme only, not credentials
        config.warehouse.type,
        config.object_storage.type,
        config.logging.level,
    )

    return config


def reset_config_cache() -> None:
    """Clear the cached configuration (useful in tests)."""
    get_config.cache_clear()
