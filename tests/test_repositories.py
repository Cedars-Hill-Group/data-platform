"""Tests for data_platform.repositories."""

from __future__ import annotations

from data_platform.ontology_adapter import Company, Person, Project
from data_platform.repositories.companies import CompanyRepository
from data_platform.repositories.normalization import (
    normalize_company_name,
    normalize_person_name,
    normalize_website_domain,
)
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


# ---------------------------------------------------------------------------
# Normalization functions
# ---------------------------------------------------------------------------


class TestNormalizeCompanyName:
    def test_lowercases(self):
        assert normalize_company_name("ACME") == "acme"

    def test_strips_corp_suffix(self):
        assert normalize_company_name("Acme Corp") == "acme"

    def test_strips_inc_suffix_with_period(self):
        assert normalize_company_name("Acme, Inc.") == "acme"

    def test_strips_multiple_suffixes(self):
        # "Corp, Inc." should be stripped iteratively
        assert normalize_company_name("Acme Corp, Inc.") == "acme"

    def test_strips_llc(self):
        assert normalize_company_name("Beta Technologies LLC") == "beta technologies"

    def test_strips_ltd(self):
        assert normalize_company_name("Widgets Ltd") == "widgets"

    def test_strips_limited(self):
        assert normalize_company_name("Widgets Limited") == "widgets"

    def test_strips_gmbh(self):
        assert normalize_company_name("Müller GmbH") == "muller"

    def test_strips_punctuation(self):
        assert normalize_company_name("Acme & Co.") == "acme"

    def test_empty_after_suffix_removal(self):
        # A name that is only a suffix should not crash
        result = normalize_company_name("Inc.")
        assert isinstance(result, str)

    def test_no_suffix(self):
        assert normalize_company_name("  Acme  ") == "acme"

    def test_preserves_multi_word_core(self):
        assert normalize_company_name("Blue Sky Ventures Inc.") == "blue sky ventures"


class TestNormalizePersonName:
    def test_lowercases(self):
        assert normalize_person_name("ALICE SMITH") == "alice smith"

    def test_strips_middle_initial(self):
        assert normalize_person_name("John D. Smith") == "john smith"

    def test_strips_middle_initial_without_period(self):
        assert normalize_person_name("John D Smith") == "john smith"

    def test_collapses_whitespace(self):
        assert normalize_person_name("  Alice   Jones  ") == "alice jones"

    def test_single_name_preserved(self):
        # Single-token names (e.g., mononyms) are not dropped
        assert normalize_person_name("Madonna") == "madonna"

    def test_two_initials_not_dropped_for_first_name(self):
        # "J. Smith" has only 2 tokens after normalization – both are kept
        # so that we never reduce a two-part name to a single token.
        result = normalize_person_name("J. Smith")
        assert result == "j smith"


class TestNormalizeWebsiteDomain:
    def test_strips_https_scheme(self):
        assert normalize_website_domain("https://acme.com") == "acme.com"

    def test_strips_http_scheme(self):
        assert normalize_website_domain("http://acme.com") == "acme.com"

    def test_strips_www(self):
        assert normalize_website_domain("https://www.acme.com") == "acme.com"

    def test_strips_path(self):
        assert normalize_website_domain("https://acme.com/about") == "acme.com"

    def test_strips_query(self):
        assert normalize_website_domain("https://acme.com?ref=footer") == "acme.com"

    def test_bare_domain(self):
        assert normalize_website_domain("acme.com") == "acme.com"

    def test_lowercases(self):
        assert normalize_website_domain("HTTPS://ACME.COM") == "acme.com"

    def test_strips_port(self):
        assert normalize_website_domain("https://acme.com:8080/path") == "acme.com"


# ---------------------------------------------------------------------------
# CompanyRepository – secondary indexes and entity resolution
# ---------------------------------------------------------------------------


class TestCompanyRepositoryResolution:
    def _repo(self) -> CompanyRepository:
        return CompanyRepository()

    def test_find_by_normalized_name_strips_suffix(self):
        repo = self._repo()
        repo.save(Company(id="c1", name="Acme Corp"))
        assert repo.find_by_normalized_name("Acme") is not None
        assert repo.find_by_normalized_name("Acme").id == "c1"

    def test_find_by_normalized_name_case_insensitive(self):
        repo = self._repo()
        repo.save(Company(id="c1", name="Blue Sky Ventures Inc."))
        assert repo.find_by_normalized_name("BLUE SKY VENTURES").id == "c1"

    def test_find_by_normalized_name_via_alias(self):
        repo = self._repo()
        repo.save(
            Company(
                id="c1",
                name="International Business Machines Corp",
                metadata={"aliases": ["IBM"]},
            )
        )
        assert repo.find_by_normalized_name("IBM").id == "c1"
        assert repo.find_by_normalized_name("International Business Machines").id == "c1"

    def test_find_by_normalized_name_missing(self):
        repo = self._repo()
        assert repo.find_by_normalized_name("Nonexistent") is None

    def test_find_by_website_domain_strips_www_and_scheme(self):
        repo = self._repo()
        repo.save(Company(id="c1", name="Acme", website="https://acme.com"))
        assert repo.find_by_website_domain("http://www.acme.com/about").id == "c1"

    def test_find_by_website_domain_missing(self):
        repo = self._repo()
        assert repo.find_by_website_domain("https://unknown.example.com") is None

    def test_find_by_website_domain_no_website_stored(self):
        repo = self._repo()
        repo.save(Company(id="c1", name="Acme"))
        assert repo.find_by_website_domain("https://acme.com") is None

    def test_resolve_by_domain(self):
        repo = self._repo()
        kb = Company(id="c1", name="Acme Corp", website="https://acme.com")
        repo.save(kb)
        probe = Company(name="ACME Incorporated", website="https://www.acme.com/")
        assert repo.resolve(probe) is kb

    def test_resolve_by_normalized_name_when_no_website(self):
        repo = self._repo()
        kb = Company(id="c1", name="Acme Corp, Inc.")
        repo.save(kb)
        probe = Company(name="acme")
        assert repo.resolve(probe) is kb

    def test_resolve_prefers_domain_over_name(self):
        repo = self._repo()
        c1 = Company(id="c1", name="Acme", website="https://acme.com")
        c2 = Company(id="c2", name="Acme Corp LLC", website="https://other.com")
        repo.save(c1)
        repo.save(c2)
        # Probe has domain matching c1 but name normalising to c2's name
        probe = Company(name="Acme Corp", website="https://acme.com")
        assert repo.resolve(probe) is c1

    def test_resolve_returns_none_when_no_match(self):
        repo = self._repo()
        repo.save(Company(id="c1", name="Acme"))
        assert repo.resolve(Company(name="Totally Unknown Co")) is None

    def test_save_updates_name_index_on_overwrite(self):
        repo = self._repo()
        repo.save(Company(id="c1", name="Old Name Corp"))
        # Old normalized form should now point to c1
        assert repo.find_by_normalized_name("old name") is not None
        # Overwrite with new name
        repo.save(Company(id="c1", name="New Name LLC"))
        assert repo.find_by_normalized_name("new name") is not None
        # Old name should no longer be in the index
        assert repo.find_by_normalized_name("old name") is None

    def test_save_updates_domain_index_on_overwrite(self):
        repo = self._repo()
        repo.save(Company(id="c1", name="Acme", website="https://old.com"))
        assert repo.find_by_website_domain("old.com") is not None
        repo.save(Company(id="c1", name="Acme", website="https://new.com"))
        assert repo.find_by_website_domain("new.com") is not None
        assert repo.find_by_website_domain("old.com") is None

    def test_delete_cleans_name_index(self):
        repo = self._repo()
        repo.save(Company(id="c1", name="Acme Corp"))
        repo.delete("c1")
        assert repo.find_by_normalized_name("acme") is None

    def test_delete_cleans_domain_index(self):
        repo = self._repo()
        repo.save(Company(id="c1", name="Acme", website="https://acme.com"))
        repo.delete("c1")
        assert repo.find_by_website_domain("acme.com") is None

    def test_initial_store_is_indexed(self):
        initial = {
            "c1": Company(id="c1", name="Seed Corp", website="https://seed.io"),
        }
        repo = CompanyRepository(store=initial)
        assert repo.find_by_normalized_name("seed") is not None
        assert repo.find_by_website_domain("seed.io") is not None


# ---------------------------------------------------------------------------
# PeopleRepository – secondary indexes and entity resolution
# ---------------------------------------------------------------------------


class TestPeopleRepositoryResolution:
    def _repo(self) -> PeopleRepository:
        return PeopleRepository()

    def test_find_by_email_uses_index(self):
        repo = self._repo()
        repo.save(Person(id="p1", name="Alice", email="alice@example.com"))
        assert repo.find_by_email("ALICE@EXAMPLE.COM").id == "p1"

    def test_find_by_normalized_name(self):
        repo = self._repo()
        repo.save(Person(id="p1", name="John D. Smith"))
        assert repo.find_by_normalized_name("John Smith").id == "p1"

    def test_find_by_normalized_name_case_insensitive(self):
        repo = self._repo()
        repo.save(Person(id="p1", name="Alice Jones"))
        assert repo.find_by_normalized_name("ALICE JONES").id == "p1"

    def test_find_by_normalized_name_missing(self):
        repo = self._repo()
        assert repo.find_by_normalized_name("Nobody Here") is None

    def test_find_by_external_id(self):
        repo = self._repo()
        repo.save(
            Person(
                id="p1",
                name="Alice",
                metadata={"external_ids": {"linkedin": "alice-smith", "github": "asmith"}},
            )
        )
        assert repo.find_by_external_id("LinkedIn", "Alice-Smith").id == "p1"
        assert repo.find_by_external_id("github", "asmith").id == "p1"

    def test_find_by_external_id_missing(self):
        repo = self._repo()
        assert repo.find_by_external_id("linkedin", "nobody") is None

    def test_resolve_by_email(self):
        repo = self._repo()
        kb = Person(id="p1", name="Alice Smith", email="alice@example.com")
        repo.save(kb)
        probe = Person(name="Alice D. Smith", email="alice@example.com")
        assert repo.resolve(probe) is kb

    def test_resolve_by_external_id_when_no_email(self):
        repo = self._repo()
        kb = Person(
            id="p1",
            name="Alice",
            metadata={"external_ids": {"linkedin": "alice-smith"}},
        )
        repo.save(kb)
        probe = Person(name="Alice", metadata={"external_ids": {"linkedin": "alice-smith"}})
        assert repo.resolve(probe) is kb

    def test_resolve_by_normalized_name(self):
        repo = self._repo()
        kb = Person(id="p1", name="Alice Smith")
        repo.save(kb)
        probe = Person(name="Alice M. Smith")
        assert repo.resolve(probe) is kb

    def test_resolve_prefers_email_over_name(self):
        repo = self._repo()
        p1 = Person(id="p1", name="Alice Smith", email="alice@example.com")
        p2 = Person(id="p2", name="Alice Smith", email="alice2@example.com")
        repo.save(p1)
        repo.save(p2)
        probe = Person(name="Alice Smith", email="alice@example.com")
        assert repo.resolve(probe) is p1

    def test_resolve_returns_none_when_no_match(self):
        repo = self._repo()
        repo.save(Person(id="p1", name="Alice Smith"))
        assert repo.resolve(Person(name="Totally Different Person")) is None

    def test_save_updates_email_index_on_overwrite(self):
        repo = self._repo()
        repo.save(Person(id="p1", name="Alice", email="old@example.com"))
        assert repo.find_by_email("old@example.com") is not None
        repo.save(Person(id="p1", name="Alice", email="new@example.com"))
        assert repo.find_by_email("new@example.com") is not None
        assert repo.find_by_email("old@example.com") is None

    def test_save_updates_name_index_on_overwrite(self):
        repo = self._repo()
        repo.save(Person(id="p1", name="Old Name"))
        assert repo.find_by_normalized_name("old name") is not None
        repo.save(Person(id="p1", name="New Name"))
        assert repo.find_by_normalized_name("new name") is not None
        assert repo.find_by_normalized_name("old name") is None

    def test_save_updates_external_id_index_on_overwrite(self):
        repo = self._repo()
        repo.save(Person(id="p1", name="Alice", metadata={"external_ids": {"github": "old"}}))
        assert repo.find_by_external_id("github", "old") is not None
        repo.save(Person(id="p1", name="Alice", metadata={"external_ids": {"github": "new"}}))
        assert repo.find_by_external_id("github", "new") is not None
        assert repo.find_by_external_id("github", "old") is None

    def test_delete_cleans_email_index(self):
        repo = self._repo()
        repo.save(Person(id="p1", name="Alice", email="alice@example.com"))
        repo.delete("p1")
        assert repo.find_by_email("alice@example.com") is None

    def test_delete_cleans_name_index(self):
        repo = self._repo()
        repo.save(Person(id="p1", name="Alice Smith"))
        repo.delete("p1")
        assert repo.find_by_normalized_name("alice smith") is None

    def test_delete_cleans_external_id_index(self):
        repo = self._repo()
        repo.save(
            Person(id="p1", name="Alice", metadata={"external_ids": {"github": "asmith"}})
        )
        repo.delete("p1")
        assert repo.find_by_external_id("github", "asmith") is None

    def test_initial_store_is_indexed(self):
        initial = {
            "p1": Person(
                id="p1",
                name="Seed Person",
                email="seed@example.com",
                metadata={"external_ids": {"github": "seeduser"}},
            )
        }
        repo = PeopleRepository(store=initial)
        assert repo.find_by_email("seed@example.com") is not None
        assert repo.find_by_normalized_name("seed person") is not None
        assert repo.find_by_external_id("github", "seeduser") is not None
