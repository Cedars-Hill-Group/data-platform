"""In-memory and SQLAlchemy-backed repository for :class:`Company` objects."""

from __future__ import annotations

from data_platform.log import get_logger
from data_platform.ontology_adapter import Company
from data_platform.repositories.base import BaseRepository
from data_platform.repositories.normalization import (
    normalize_company_name,
    normalize_website_domain,
)

logger = get_logger(__name__)


class CompanyRepository(BaseRepository[Company]):
    """Repository for :class:`~data_platform.ontology_adapter.Company` objects.

    The default implementation is an in-memory store.

    In addition to the primary ``{id: Company}`` store the repository
    maintains two secondary indexes to support deterministic entity resolution
    without fuzzy matching or embeddings:

    * **Name index** – maps ``normalize_company_name(name)`` (and each alias
      stored in ``company.metadata["aliases"]``) to a company ID.
    * **Domain index** – maps ``normalize_website_domain(website)`` to a
      company ID.

    Both indexes are updated atomically on every :meth:`save` and
    :meth:`delete` call so they remain consistent with the primary store.

    Parameters
    ----------
    store:
        Optional initial store dict (``{id: Company}``).  Both secondary
        indexes are populated from the provided records during ``__init__``.
    """

    def __init__(self, store: dict[str, Company] | None = None) -> None:
        self._store: dict[str, Company] = store if store is not None else {}

        # normalized_name → company_id
        self._name_index: dict[str, str] = {}
        # company_id → set of normalized names currently indexed
        self._name_keys: dict[str, set[str]] = {}
        # normalized_domain → company_id
        self._domain_index: dict[str, str] = {}
        # company_id → normalized_domain currently indexed (at most one)
        self._domain_keys: dict[str, str] = {}

        for company in self._store.values():
            self._index_company(company)

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
        self._deindex_company(obj.id)
        self._store[obj.id] = obj
        self._index_company(obj)
        return obj

    def delete(self, object_id: str) -> bool:
        if object_id in self._store:
            self._deindex_company(object_id)
            del self._store[object_id]
            return True
        return False

    def count(self) -> int:
        return len(self._store)

    # ------------------------------------------------------------------
    # Domain-specific helpers
    # ------------------------------------------------------------------

    def find_by_name(self, name: str) -> Company | None:
        """Return the first company whose name matches (case-insensitive).

        This performs an exact case-insensitive comparison against the stored
        ``name`` field.  For a match that also strips legal suffixes and
        recognises aliases use :meth:`find_by_normalized_name`.
        """
        name_lower = name.lower()
        for company in self._store.values():
            if company.name.lower() == name_lower:
                return company
        return None

    def find_by_normalized_name(self, name: str) -> Company | None:
        """Return the company whose normalized name or alias matches *name*.

        The query *name* is passed through :func:`.normalize_company_name`
        before the lookup, so legal suffixes, punctuation, and case
        differences are all ignored.

        Companies can register additional name variants (trade names,
        abbreviations, former names) by populating
        ``company.metadata["aliases"]`` with a list of strings.  All aliases
        are indexed on :meth:`save`.

        Examples
        --------
        ::

            # "Acme Corp, Inc." and "ACME" both resolve to the same company.
            repo.save(Company(id="c1", name="Acme Corp, Inc."))
            repo.find_by_normalized_name("ACME")         # → Company c1
            repo.find_by_normalized_name("acme corp")    # → Company c1
        """
        norm = normalize_company_name(name)
        oid = self._name_index.get(norm)
        return self._store.get(oid) if oid else None  # type: ignore[arg-type]

    def find_by_website_domain(self, url: str) -> Company | None:
        """Return the company whose website domain matches the domain in *url*.

        The domain is extracted and normalized via
        :func:`.normalize_website_domain`, so scheme, ``www.`` prefix, paths,
        and ports are all ignored.

        Examples
        --------
        ::

            repo.save(Company(id="c1", name="Acme", website="https://acme.com"))
            repo.find_by_website_domain("http://www.acme.com/about")  # → Company c1
        """
        domain = normalize_website_domain(url)
        oid = self._domain_index.get(domain)
        return self._store.get(oid) if oid else None  # type: ignore[arg-type]

    def find_by_industry(self, industry: str) -> list[Company]:
        """Return all companies in the given *industry*."""
        return self.list(industry=industry)

    def resolve(self, candidate: Company) -> Company | None:
        """Attempt to find *candidate* in the repository using a tiered strategy.

        Tiers are applied in order; the first match wins:

        1. **Website domain** – normalized domain extracted from
           ``candidate.website`` (when present).
        2. **Normalized name** – ``candidate.name`` passed through
           :func:`.normalize_company_name`, matched against the name index
           which includes any stored aliases.

        Returns the matching :class:`Company`, or ``None`` when no match is
        found (signal that LLM-assisted disambiguation may be warranted).

        Examples
        --------
        ::

            kb_company = Company(id="c1", name="Acme Corp", website="https://acme.com")
            repo.save(kb_company)

            # Resolves via domain even when name differs
            probe = Company(name="ACME Incorporated", website="https://www.acme.com")
            repo.resolve(probe)  # → kb_company
        """
        if candidate.website:
            match = self.find_by_website_domain(candidate.website)
            if match:
                return match
        return self.find_by_normalized_name(candidate.name)

    # ------------------------------------------------------------------
    # Internal index management
    # ------------------------------------------------------------------

    def _index_company(self, company: Company) -> None:
        """Add *company* to both secondary indexes."""
        oid = company.id

        # Collect all normalized name forms: canonical name + aliases.
        names: set[str] = set()
        norm_name = normalize_company_name(company.name)
        if norm_name:
            names.add(norm_name)
        for alias in company.metadata.get("aliases", []):
            norm_alias = normalize_company_name(str(alias))
            if norm_alias:
                names.add(norm_alias)

        self._name_keys[oid] = names
        for norm in names:
            if norm in self._name_index and self._name_index[norm] != oid:
                logger.warning(
                    "Company name collision: normalized form %r already maps to id %r; "
                    "overwriting with id %r",
                    norm,
                    self._name_index[norm],
                    oid,
                )
            self._name_index[norm] = oid

        # Website domain index (at most one domain per company).
        if company.website:
            domain = normalize_website_domain(company.website)
            if domain:
                if domain in self._domain_index and self._domain_index[domain] != oid:
                    logger.warning(
                        "Company domain collision: domain %r already maps to id %r; "
                        "overwriting with id %r",
                        domain,
                        self._domain_index[domain],
                        oid,
                    )
                self._domain_index[domain] = oid
                self._domain_keys[oid] = domain

    def _deindex_company(self, object_id: str) -> None:
        """Remove *object_id* from both secondary indexes."""
        for norm_name in self._name_keys.pop(object_id, set()):
            self._name_index.pop(norm_name, None)
        domain = self._domain_keys.pop(object_id, None)
        if domain:
            self._domain_index.pop(domain, None)
