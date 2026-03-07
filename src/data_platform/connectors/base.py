"""Abstract base connector interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseConnector(ABC):
    """Common interface that every storage connector must implement.

    Connectors are context-manager aware::

        with DatabaseConnector(config) as conn:
            conn.execute("SELECT 1")
    """

    @abstractmethod
    def connect(self) -> None:
        """Open the underlying connection / session."""

    @abstractmethod
    def disconnect(self) -> None:
        """Close the underlying connection / session."""

    @abstractmethod
    def is_connected(self) -> bool:
        """Return ``True`` when the connection is open and healthy."""

    @abstractmethod
    def execute(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Execute a query/command and return results as a list of dicts.

        Parameters
        ----------
        query:
            SQL statement or connector-specific command string.
        params:
            Optional bound parameters (use named placeholders, e.g. ``:name``).
        """

    def __enter__(self) -> "BaseConnector":
        self.connect()
        return self

    def __exit__(self, *_: object) -> None:
        self.disconnect()
