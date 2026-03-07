"""Analytical data warehouse connector.

Provides a thin abstraction over BigQuery, Snowflake, and Redshift backends.
The connector delegates to the appropriate SQLAlchemy dialect (which must be
installed separately as an optional dependency).

Supported ``type`` values in :class:`~data_platform.config.WarehouseConfig`:
- ``bigquery``  – requires ``sqlalchemy-bigquery``
- ``snowflake`` – requires ``snowflake-sqlalchemy``
- ``redshift``  – requires ``sqlalchemy-redshift``
- ``none``      – no-op connector (default)
"""

from __future__ import annotations

from typing import Any

from data_platform.config import WarehouseConfig
from data_platform.connectors.base import BaseConnector


class WarehouseConnector(BaseConnector):
    """Connects to a cloud data warehouse.

    The connector builds the appropriate connection string from the supplied
    :class:`~data_platform.config.WarehouseConfig` and delegates execution to
    SQLAlchemy.

    Parameters
    ----------
    config:
        Warehouse configuration (type, credentials, etc.).
    """

    def __init__(self, config: WarehouseConfig) -> None:
        self._config = config
        self._engine: Any = None

    # ------------------------------------------------------------------
    # BaseConnector interface
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Initialise the warehouse engine based on the configured type."""
        wtype = self._config.type.lower()
        if wtype == "none":
            return  # no-op
        url = self._build_url(wtype)
        try:
            from sqlalchemy import create_engine  # noqa: PLC0415

            self._engine = create_engine(url)
        except ImportError as exc:
            raise ImportError(
                f"Missing SQLAlchemy dialect for warehouse type '{wtype}'. "
                f"Install the required package (e.g. sqlalchemy-bigquery)."
            ) from exc

    def disconnect(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None

    def is_connected(self) -> bool:
        return self._engine is not None

    def execute(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Execute a query against the warehouse and return rows as dicts."""
        if not self.is_connected():
            raise RuntimeError("Warehouse not connected. Call connect() first.")
        from sqlalchemy import text  # noqa: PLC0415

        with self._engine.connect() as conn:
            result = conn.execute(text(query), params or {})
            if result.returns_rows:
                keys = list(result.keys())
                return [dict(zip(keys, row)) for row in result.fetchall()]
            return []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_url(self, wtype: str) -> str:
        cfg = self._config
        if wtype == "bigquery":
            if not cfg.project or not cfg.dataset:
                raise ValueError("BigQuery requires 'project' and 'dataset' in warehouse config.")
            return f"bigquery://{cfg.project}/{cfg.dataset}"
        if wtype == "snowflake":
            if not all([cfg.account, cfg.user, cfg.password, cfg.warehouse, cfg.database]):
                raise ValueError(
                    "Snowflake requires account, user, password, warehouse, and database."
                )
            schema = cfg.schema_name or "PUBLIC"
            return (
                f"snowflake://{cfg.user}:{cfg.password}@{cfg.account}/"
                f"{cfg.database}/{schema}?warehouse={cfg.warehouse}"
            )
        if wtype == "redshift":
            if not all([cfg.user, cfg.password, cfg.database]):
                raise ValueError("Redshift requires user, password, and database in config.")
            host = cfg.account or "localhost"
            return f"redshift+psycopg2://{cfg.user}:{cfg.password}@{host}:5439/{cfg.database}"
        raise ValueError(
            f"Unsupported warehouse type: '{wtype}'. Choose bigquery, snowflake, redshift, or none."
        )
