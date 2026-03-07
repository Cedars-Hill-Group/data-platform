"""In-memory and SQLAlchemy-backed repository for :class:`Project` objects."""

from __future__ import annotations

from data_platform.ontology_adapter import Project
from data_platform.repositories.base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    """Repository for :class:`~data_platform.ontology_adapter.Project` objects.

    The default implementation is an in-memory store.

    Parameters
    ----------
    store:
        Optional initial store dict (``{id: Project}``).
    """

    def __init__(self, store: dict[str, Project] | None = None) -> None:
        self._store: dict[str, Project] = store if store is not None else {}

    # ------------------------------------------------------------------
    # BaseRepository implementation
    # ------------------------------------------------------------------

    def get(self, object_id: str) -> Project | None:
        return self._store.get(object_id)

    def list(self, **filters: object) -> list[Project]:
        """Return projects, optionally filtered by field values.

        Examples
        --------
        ::

            repo.list(status="active")
            repo.list(owner="alice@example.com")
        """
        results = list(self._store.values())
        for field, value in filters.items():
            results = [p for p in results if getattr(p, field, None) == value]
        return results

    def save(self, obj: Project) -> Project:
        self._store[obj.id] = obj
        return obj

    def delete(self, object_id: str) -> bool:
        if object_id in self._store:
            del self._store[object_id]
            return True
        return False

    def count(self) -> int:
        return len(self._store)

    # ------------------------------------------------------------------
    # Domain-specific helpers
    # ------------------------------------------------------------------

    def find_by_owner(self, owner: str) -> list[Project]:
        """Return all projects owned by *owner*."""
        return self.list(owner=owner)

    def find_by_status(self, status: str) -> list[Project]:
        """Return all projects with the given *status*."""
        return self.list(status=status)

    def find_by_member(self, member: str) -> list[Project]:
        """Return all projects that include *member* in their members list."""
        return [p for p in self._store.values() if member in p.members]
