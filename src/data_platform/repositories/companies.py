"""In-memory and SQLAlchemy-backed repository for :class:`Company` objects."""

from __future__ import annotations

from data_platform.ontology_adapter import Company
from data_platform.repositories.base import BaseRepository


class CompanyRepository(BaseRepository[Company]):
    """Repository for :class:`~data_platform.ontology_adapter.Company` objects.

    The default implementation is an in-memory store.

    Parameters
    ----------
    store:
        Optional initial store dict (``{id: Company}``).
    """

    def __init__(self, store: dict[str, Company] | None = None) -> None:
        self._store: dict[str, Company] = store if store is not None else {}

    # ------------------------------------------------------------------
    # BaseRepository implementation
    # ------------------------------------------------------------------

    def get(self, object_id: str) -> Company | None:
        return self._store.get(object_id)

    def list(self, **filters: object) -> list[Company]:
        """Return companies, optionally filtered by field values.

        Examples
        --------
        ::

            repo.list(industry="Technology")
            repo.list(size="Large")
        """
        results = list(self._store.values())
        for field, value in filters.items():
            results = [c for c in results if getattr(c, field, None) == value]
        return results

    def save(self, obj: Company) -> Company:
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

    def find_by_name(self, name: str) -> Company | None:
        """Return the first company whose name matches (case-insensitive)."""
        name_lower = name.lower()
        for company in self._store.values():
            if company.name.lower() == name_lower:
                return company
        return None

    def find_by_industry(self, industry: str) -> list[Company]:
        """Return all companies in the given *industry*."""
        return self.list(industry=industry)
