"""Tests for data_platform.repositories."""

from __future__ import annotations

import pytest

from data_platform.ontology_adapter import Company, Person, Project
from data_platform.repositories.companies import CompanyRepository
from data_platform.repositories.people import PeopleRepository
from data_platform.repositories.projects import ProjectRepository


# ---------------------------------------------------------------------------
# PeopleRepository
# ---------------------------------------------------------------------------


class TestPeopleRepository:
    def _repo(self) -> PeopleRepository:
        return PeopleRepository()

    def test_save_and_get(self):
        repo = self._repo()
        person = Person(id="p1", name="Alice", email="alice@example.com")
        saved = repo.save(person)
        assert saved is person
        assert repo.get("p1") is person

    def test_get_missing_returns_none(self):
        assert self._repo().get("nonexistent") is None

    def test_list_all(self):
        repo = self._repo()
        repo.save(Person(id="p1", name="Alice"))
        repo.save(Person(id="p2", name="Bob"))
        assert len(repo.list()) == 2

    def test_list_with_filter(self):
        repo = self._repo()
        repo.save(Person(id="p1", name="Alice", organization="Acme"))
        repo.save(Person(id="p2", name="Bob", organization="Beta"))
        results = repo.list(organization="Acme")
        assert len(results) == 1
        assert results[0].name == "Alice"

    def test_delete_existing(self):
        repo = self._repo()
        repo.save(Person(id="p1", name="Alice"))
        assert repo.delete("p1") is True
        assert repo.get("p1") is None

    def test_delete_missing_returns_false(self):
        assert self._repo().delete("ghost") is False

    def test_count(self):
        repo = self._repo()
        assert repo.count() == 0
        repo.save(Person(id="p1", name="Alice"))
        assert repo.count() == 1

    def test_find_by_email(self):
        repo = self._repo()
        repo.save(Person(id="p1", name="Alice", email="alice@example.com"))
        result = repo.find_by_email("ALICE@EXAMPLE.COM")
        assert result is not None
        assert result.name == "Alice"

    def test_find_by_email_missing(self):
        assert self._repo().find_by_email("nobody@example.com") is None

    def test_find_by_organization(self):
        repo = self._repo()
        repo.save(Person(id="p1", name="Alice", organization="Acme"))
        repo.save(Person(id="p2", name="Bob", organization="Beta"))
        results = repo.find_by_organization("Acme")
        assert len(results) == 1

    def test_save_updates_existing(self):
        repo = self._repo()
        repo.save(Person(id="p1", name="Alice", role="Engineer"))
        repo.save(Person(id="p1", name="Alice", role="Lead Engineer"))
        assert repo.get("p1").role == "Lead Engineer"
        assert repo.count() == 1


# ---------------------------------------------------------------------------
# CompanyRepository
# ---------------------------------------------------------------------------


class TestCompanyRepository:
    def _repo(self) -> CompanyRepository:
        return CompanyRepository()

    def test_save_and_get(self):
        repo = self._repo()
        company = Company(id="c1", name="Acme Corp")
        repo.save(company)
        assert repo.get("c1") is company

    def test_list_with_filter(self):
        repo = self._repo()
        repo.save(Company(id="c1", name="Acme", industry="Tech"))
        repo.save(Company(id="c2", name="Beta", industry="Finance"))
        results = repo.list(industry="Tech")
        assert len(results) == 1

    def test_delete(self):
        repo = self._repo()
        repo.save(Company(id="c1", name="Acme"))
        assert repo.delete("c1") is True
        assert repo.count() == 0

    def test_find_by_name(self):
        repo = self._repo()
        repo.save(Company(id="c1", name="Acme Corp"))
        result = repo.find_by_name("acme corp")
        assert result is not None

    def test_find_by_industry(self):
        repo = self._repo()
        repo.save(Company(id="c1", name="Acme", industry="Tech"))
        assert len(repo.find_by_industry("Tech")) == 1


# ---------------------------------------------------------------------------
# ProjectRepository
# ---------------------------------------------------------------------------


class TestProjectRepository:
    def _repo(self) -> ProjectRepository:
        return ProjectRepository()

    def test_save_and_get(self):
        repo = self._repo()
        project = Project(id="pr1", name="Alpha", owner="alice@example.com")
        repo.save(project)
        assert repo.get("pr1").name == "Alpha"

    def test_find_by_owner(self):
        repo = self._repo()
        repo.save(Project(id="pr1", name="Alpha", owner="alice@example.com"))
        repo.save(Project(id="pr2", name="Beta", owner="bob@example.com"))
        results = repo.find_by_owner("alice@example.com")
        assert len(results) == 1

    def test_find_by_status(self):
        repo = self._repo()
        repo.save(Project(id="pr1", name="Alpha", status="active"))
        repo.save(Project(id="pr2", name="Beta", status="archived"))
        assert len(repo.find_by_status("active")) == 1

    def test_find_by_member(self):
        repo = self._repo()
        repo.save(
            Project(id="pr1", name="Alpha", members=["alice@example.com", "bob@example.com"])
        )
        repo.save(Project(id="pr2", name="Beta", members=["carol@example.com"]))
        results = repo.find_by_member("alice@example.com")
        assert len(results) == 1
        assert results[0].name == "Alpha"

    def test_count_and_delete(self):
        repo = self._repo()
        repo.save(Project(id="pr1", name="Alpha"))
        assert repo.count() == 1
        repo.delete("pr1")
        assert repo.count() == 0
