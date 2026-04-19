"""In-memory and SQLAlchemy-backed repository for :class:`Person` objects."""

from __future__ import annotations

from data_platform.ontology_adapter import Person
from data_platform.repositories.base import BaseRepository
from data_platform.repositories.normalization import normalize_person_name


class PeopleRepository(BaseRepository[Person]):
    """Repository for :class:`~data_platform.ontology_adapter.Person` objects.

    The default implementation is an in-memory store (a plain dict) suitable
    for tests and small datasets.  Swap in a database-backed subclass for
    production use.

    In addition to the primary ``{id: Person}`` store the repository
    maintains three secondary indexes to support deterministic entity
    resolution without fuzzy matching or embeddings:

    * **Email index** – maps ``email.lower()`` to a person ID.
    * **Name index** – maps ``normalize_person_name(name)`` to a person ID.
    * **External-ID index** – maps ``(platform, handle)`` tuples (both
      lowercased) to a person ID.  External IDs are stored in
      ``person.metadata["external_ids"]`` as a ``{platform: handle}`` dict,
      e.g. ``{"linkedin": "alice-smith", "github": "asmith"}``.

    All indexes are updated atomically on every :meth:`save` and
    :meth:`delete` call so they remain consistent with the primary store.

    Parameters
    ----------
    store:
        Optional initial store dict (``{id: Person}``).  Defaults to an empty
        dict so the repository starts fresh.
    """

    def __init__(self, store: dict[str, Person] | None = None) -> None:
        self._store: dict[str, Person] = store if store is not None else {}

        # email_lower → person_id
        self._email_index: dict[str, str] = {}
        # person_id → email_lower currently indexed
        self._email_keys: dict[str, str] = {}
        # normalized_name → person_id
        self._name_index: dict[str, str] = {}
        # person_id → normalized_name currently indexed
        self._name_keys: dict[str, str] = {}
        # (platform_lower, handle_lower) → person_id
        self._ext_id_index: dict[tuple[str, str], str] = {}
        # person_id → list of (platform_lower, handle_lower) currently indexed
        self._ext_id_keys: dict[str, list[tuple[str, str]]] = {}

        for person in self._store.values():
            self._index_person(person)

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
        self._deindex_person(obj.id)
        self._store[obj.id] = obj
        self._index_person(obj)
        return obj

    def delete(self, object_id: str) -> bool:
        if object_id in self._store:
            self._deindex_person(object_id)
            del self._store[object_id]
            return True
        return False

    def count(self) -> int:
        return len(self._store)

    # ------------------------------------------------------------------
    # Domain-specific helpers
    # ------------------------------------------------------------------

    def find_by_email(self, email: str) -> Person | None:
        """Return the person whose email matches (case-insensitive).

        Uses the email index for O(1) lookup.
        """
        oid = self._email_index.get(email.lower())
        return self._store.get(oid) if oid else None  # type: ignore[arg-type]

    def find_by_normalized_name(self, name: str) -> Person | None:
        """Return the person whose name normalises to the same form as *name*.

        The query *name* is passed through :func:`.normalize_person_name`
        before the lookup, so middle initials, punctuation, and case
        differences are all ignored.

        Examples
        --------
        ::

            repo.save(Person(id="p1", name="John D. Smith"))
            repo.find_by_normalized_name("John Smith")   # → Person p1
            repo.find_by_normalized_name("JOHN SMITH")   # → Person p1
        """
        norm = normalize_person_name(name)
        oid = self._name_index.get(norm)
        return self._store.get(oid) if oid else None  # type: ignore[arg-type]

    def find_by_external_id(self, platform: str, handle: str) -> Person | None:
        """Return the person identified by *handle* on *platform*.

        Both *platform* and *handle* are compared case-insensitively.
        External IDs must be stored in ``person.metadata["external_ids"]``
        as a ``{platform: handle}`` mapping before they can be looked up.

        Examples
        --------
        ::

            person = Person(
                id="p1",
                name="Alice",
                metadata={"external_ids": {"linkedin": "alice-smith"}},
            )
            repo.save(person)
            repo.find_by_external_id("LinkedIn", "Alice-Smith")  # → Person p1
        """
        key = (platform.lower(), handle.lower())
        oid = self._ext_id_index.get(key)
        return self._store.get(oid) if oid else None  # type: ignore[arg-type]

    def find_by_organization(self, organization: str) -> list[Person]:
        """Return all people belonging to *organization*."""
        return self.list(organization=organization)

    def resolve(self, candidate: Person) -> Person | None:
        """Attempt to find *candidate* in the repository using a tiered strategy.

        Tiers are applied in order; the first match wins:

        1. **Email address** – exact case-insensitive match against
           ``candidate.email`` (when present).
        2. **External identifiers** – each ``(platform, handle)`` pair from
           ``candidate.metadata["external_ids"]`` (when present).
        3. **Normalized name** – ``candidate.name`` passed through
           :func:`.normalize_person_name`.

        Returns the matching :class:`Person`, or ``None`` when no match is
        found (signal that LLM-assisted disambiguation may be warranted).

        Examples
        --------
        ::

            repo.save(Person(id="p1", name="Alice Smith", email="alice@example.com"))

            probe = Person(name="Alice D. Smith", email="alice@example.com")
            repo.resolve(probe)  # → Person p1  (matched via email)
        """
        # Tier 1a – email
        if candidate.email:
            match = self.find_by_email(candidate.email)
            if match:
                return match

        # Tier 1b – external identifiers
        for platform, handle in candidate.metadata.get("external_ids", {}).items():
            match = self.find_by_external_id(platform, str(handle))
            if match:
                return match

        # Tier 2 – normalised name
        return self.find_by_normalized_name(candidate.name)

    # ------------------------------------------------------------------
    # Internal index management
    # ------------------------------------------------------------------

    def _index_person(self, person: Person) -> None:
        """Add *person* to secondary indexes."""
        oid = person.id

        if person.email:
            email_lower = person.email.lower()
            self._email_index[email_lower] = oid
            self._email_keys[oid] = email_lower

        norm_name = normalize_person_name(person.name)
        if norm_name:
            self._name_index[norm_name] = oid
            self._name_keys[oid] = norm_name

        ext_ids: list[tuple[str, str]] = [
            (p.lower(), str(h).lower())
            for p, h in person.metadata.get("external_ids", {}).items()
        ]
        self._ext_id_keys[oid] = ext_ids
        for key in ext_ids:
            self._ext_id_index[key] = oid

    def _deindex_person(self, object_id: str) -> None:
        """Remove *object_id* from secondary indexes."""
        email = self._email_keys.pop(object_id, None)
        if email:
            self._email_index.pop(email, None)

        norm_name = self._name_keys.pop(object_id, None)
        if norm_name:
            self._name_index.pop(norm_name, None)

        for key in self._ext_id_keys.pop(object_id, []):
            self._ext_id_index.pop(key, None)
