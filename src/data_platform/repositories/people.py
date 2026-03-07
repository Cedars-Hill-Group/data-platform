"""In-memory and SQLAlchemy-backed repository for :class:`Person` objects."""

from __future__ import annotations

from data_platform.ontology_adapter import Person
from data_platform.repositories.base import BaseRepository


class PeopleRepository(BaseRepository[Person]):
    """Repository for :class:`~data_platform.ontology_adapter.Person` objects.

    The default implementation is an in-memory store (a plain dict) suitable
    for tests and small datasets.  Swap in a database-backed subclass for
    production use.

    Parameters
    ----------
    store:
        Optional initial store dict (``{id: Person}``).  Defaults to an empty
        dict so the repository starts fresh.
    """

    def __init__(self, store: dict[str, Person] | None = None) -> None:
        self._store: dict[str, Person] = store if store is not None else {}

    # ------------------------------------------------------------------
    # BaseRepository implementation
    # ------------------------------------------------------------------

    def get(self, object_id: str) -> Person | None:
        return self._store.get(object_id)

    def list(self, **filters: object) -> list[Person]:
        """Return people, optionally filtered by field values.

        Examples
        --------
        ::

            repo.list(organization="Acme")
            repo.list(role="Engineer")
        """
        results = list(self._store.values())
        for field, value in filters.items():
            results = [p for p in results if getattr(p, field, None) == value]
        return results

    def save(self, obj: Person) -> Person:
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

    def find_by_email(self, email: str) -> Person | None:
        """Return the first person whose email matches (case-insensitive)."""
        email_lower = email.lower()
        for person in self._store.values():
            if person.email and person.email.lower() == email_lower:
                return person
        return None

    def find_by_organization(self, organization: str) -> list[Person]:
        """Return all people belonging to *organization*."""
        return self.list(organization=organization)
