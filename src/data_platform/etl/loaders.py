"""Repository loaders – persist canonical objects into repository stores."""

from __future__ import annotations

from typing import Any

from data_platform.ontology_adapter import Company, Person, Project
from data_platform.repositories.base import BaseRepository


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
        for obj in objects:
            if isinstance(obj, Person) and self._people is not None:
                self._people.save(obj)
                saved += 1
            elif isinstance(obj, Company) and self._companies is not None:
                self._companies.save(obj)
                saved += 1
            elif isinstance(obj, Project) and self._projects is not None:
                self._projects.save(obj)
                saved += 1
        return saved

    def load_people(self, people: list[Person]) -> int:
        """Save a list of :class:`Person` objects. Returns count saved."""
        if self._people is None:
            return 0
        for person in people:
            self._people.save(person)
        return len(people)

    def load_companies(self, companies: list[Company]) -> int:
        """Save a list of :class:`Company` objects. Returns count saved."""
        if self._companies is None:
            return 0
        for company in companies:
            self._companies.save(company)
        return len(companies)

    def load_projects(self, projects: list[Project]) -> int:
        """Save a list of :class:`Project` objects. Returns count saved."""
        if self._projects is None:
            return 0
        for project in projects:
            self._projects.save(project)
        return len(projects)
