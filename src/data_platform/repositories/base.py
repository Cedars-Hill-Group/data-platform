"""Generic repository interface.

Repositories provide an abstraction layer between the domain model and the
underlying storage backend.  Concrete implementations can back onto a
relational database, an in-memory dict (tests), or any other store.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

ModelT = TypeVar("ModelT")


class BaseRepository(ABC, Generic[ModelT]):
    """CRUD interface for a single canonical object type.

    Type parameter ``ModelT`` is the pydantic model class (Person, Company, …).
    """

    @abstractmethod
    def get(self, object_id: str) -> ModelT | None:
        """Return the object with *object_id*, or ``None`` if not found."""

    @abstractmethod
    def list(self, **filters: object) -> list[ModelT]:
        """Return all objects, optionally filtered by keyword arguments."""

    @abstractmethod
    def save(self, obj: ModelT) -> ModelT:
        """Persist *obj* (insert or update) and return the saved instance."""

    @abstractmethod
    def delete(self, object_id: str) -> bool:
        """Delete the object with *object_id*.

        Returns ``True`` if the object existed and was removed, ``False``
        otherwise.
        """

    @abstractmethod
    def count(self) -> int:
        """Return the total number of stored objects."""
