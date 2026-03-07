"""Repository loaders – persist canonical objects into repository stores."""

from __future__ import annotations

from typing import Any

from data_platform.log import get_logger
from data_platform.ontology_adapter import Company, Person, Project
from data_platform.repositories.base import BaseRepository

logger = get_logger(__name__)


class RepositoryLoader:
    """Saves a batch of canonical objects into their respective repositories.

    Parameters
    ----------
    people_repo:
        Repository for :class:`~data_platform.ontology_adapter.Person` objects.
    companies_repo:
        Repository for :class:`~data_platform.ontology_adapter.Company` objects.
    projects_repo:
        Repository for :class:`~data_platform.ontology_adapter.Project` objects.
    """

    def __init__(
        self,
        people_repo: BaseRepository[Person] | None = None,
        companies_repo: BaseRepository[Company] | None = None,
        projects_repo: BaseRepository[Project] | None = None,
    ) -> None:
        self._people = people_repo
        self._companies = companies_repo
        self._projects = projects_repo

    def load(self, objects: list[Any]) -> int:
        """Save each object to its matching repository.

        Objects are routed by type (``Person`` → people_repo, etc.).
        Objects whose type has no configured repository are skipped.

        Parameters
        ----------
        objects:
            Mixed list of canonical model instances.

        Returns
        -------
        int
            Total number of objects successfully saved.
        """
        saved = 0
        skipped = 0
        for obj in objects:
            if isinstance(obj, Person) and self._people is not None:
                self._people.save(obj)
                logger.debug("Saved Person id=%s", obj.id)
                saved += 1
            elif isinstance(obj, Company) and self._companies is not None:
                self._companies.save(obj)
                logger.debug("Saved Company id=%s", obj.id)
                saved += 1
            elif isinstance(obj, Project) and self._projects is not None:
                self._projects.save(obj)
                logger.debug("Saved Project id=%s", obj.id)
                saved += 1
            else:
                logger.debug(
                    "Skipped %s id=%s (no repository configured)",
                    type(obj).__name__,
                    getattr(obj, "id", "?"),
                )
                skipped += 1
        logger.info("RepositoryLoader: saved=%d skipped=%d", saved, skipped)
        return saved

    def load_people(self, people: list[Person]) -> int:
        """Save a list of :class:`Person` objects. Returns count saved."""
        if self._people is None:
            logger.debug("load_people: no people_repo configured; skipping %d record(s)", len(people))
            return 0
        for person in people:
            self._people.save(person)
        logger.info("Loaded %d Person record(s)", len(people))
        return len(people)

    def load_companies(self, companies: list[Company]) -> int:
        """Save a list of :class:`Company` objects. Returns count saved."""
        if self._companies is None:
            logger.debug("load_companies: no companies_repo configured; skipping %d record(s)", len(companies))
            return 0
        for company in companies:
            self._companies.save(company)
        logger.info("Loaded %d Company record(s)", len(companies))
        return len(companies)

    def load_projects(self, projects: list[Project]) -> int:
        """Save a list of :class:`Project` objects. Returns count saved."""
        if self._projects is None:
            logger.debug("load_projects: no projects_repo configured; skipping %d record(s)", len(projects))
            return 0
        for project in projects:
            self._projects.save(project)
        logger.info("Loaded %d Project record(s)", len(projects))
        return len(projects)
