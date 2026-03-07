"""SQLAlchemy-backed relational database connector."""

from __future__ import annotations

from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from data_platform.config import DatabaseConfig
from data_platform.connectors.base import BaseConnector
from data_platform.log import get_logger

logger = get_logger(__name__)


class DatabaseConnector(BaseConnector):
    """Connects to any SQLAlchemy-compatible relational database.

    Parameters
    ----------
    config:
        :class:`~data_platform.config.DatabaseConfig` instance (or any object
        with a ``url`` attribute).

    Examples
    --------
    ::

        from data_platform.config import get_config
        from data_platform.connectors.database import DatabaseConnector

        with DatabaseConnector(get_config().database) as db:
            rows = db.execute("SELECT * FROM people")
    """

    def __init__(self, config: DatabaseConfig) -> None:
        self._config = config
        self._engine: Engine | None = None
        self._Session: type[Session] | None = None  # noqa: N806

    # ------------------------------------------------------------------
    # BaseConnector interface
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Create the SQLAlchemy engine and session factory."""
        scheme = self._config.url.split("://")[0]
        logger.info("Connecting to database (scheme=%s)", scheme)
        kwargs: dict[str, Any] = {"echo": self._config.echo}
        # pool_size / max_overflow are only valid for non-SQLite engines
        if not self._config.url.startswith("sqlite"):
            kwargs["pool_size"] = self._config.pool_size
            kwargs["max_overflow"] = self._config.max_overflow
        self._engine = create_engine(self._config.url, **kwargs)
        self._Session = sessionmaker(bind=self._engine)
        logger.debug("Database engine created (scheme=%s, pool_size=%s)", scheme, kwargs.get("pool_size", "N/A"))

    def disconnect(self) -> None:
        """Dispose of the connection pool."""
        if self._engine is not None:
            scheme = self._config.url.split("://")[0]
            logger.info("Disconnecting from database (scheme=%s)", scheme)
            self._engine.dispose()
            self._engine = None
            self._Session = None
            logger.debug("Database engine disposed")

    def is_connected(self) -> bool:
        return self._engine is not None

    def execute(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Execute a raw SQL statement and return rows as dicts."""
        if not self.is_connected():
            raise RuntimeError("Not connected. Call connect() first.")
        assert self._engine is not None
        # Truncate the query in the log to avoid logging sensitive data.
        stripped_query = query.strip()
        truncated = stripped_query[:120].replace("\n", " ")
        logger.debug("Executing SQL: %s%s", truncated, "…" if len(stripped_query) > 120 else "")
        with self._engine.begin() as conn:
            result = conn.execute(text(query), params or {})
            if result.returns_rows:
                keys = list(result.keys())
                rows = [dict(zip(keys, row)) for row in result.fetchall()]
                logger.debug("Query returned %d row(s)", len(rows))
                return rows
            return []

    # ------------------------------------------------------------------
    # Session helper (for ORM usage)
    # ------------------------------------------------------------------

    def session(self) -> Session:
        """Return a new SQLAlchemy :class:`~sqlalchemy.orm.Session`."""
        if self._Session is None:
            raise RuntimeError("Not connected. Call connect() first.")
        return self._Session()

    @property
    def engine(self) -> Engine:
        """The underlying SQLAlchemy :class:`~sqlalchemy.engine.Engine`."""
        if self._engine is None:
            raise RuntimeError("Not connected. Call connect() first.")
        return self._engine
