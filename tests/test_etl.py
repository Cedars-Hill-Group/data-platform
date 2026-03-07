"""Tests for data_platform.etl – transformers, loaders, and pipelines."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from data_platform.etl.base import ETLPipeline, ETLResult
from data_platform.etl.loaders import RepositoryLoader
from data_platform.etl.markdown_loader import MarkdownETLPipeline
from data_platform.etl.transformers import (
    CompanyTransformer,
    PersonTransformer,
    ProjectTransformer,
    RawDocument,
)
from data_platform.knowledge_base.reader import KnowledgeBaseReader
from data_platform.ontology_adapter import Company, Person, Project
from data_platform.repositories.companies import CompanyRepository
from data_platform.repositories.people import PeopleRepository
from data_platform.repositories.projects import ProjectRepository


# ---------------------------------------------------------------------------
# RawDocument
# ---------------------------------------------------------------------------


class TestRawDocument:
    def test_from_parsed(self, kb_root: Path):
        reader = KnowledgeBaseReader(kb_root)
        doc = reader.read_file(kb_root / "people" / "alice-smith.md")
        raw = RawDocument.from_parsed(doc)
        assert raw.object_type == "person"
        assert raw.data["name"] == "Alice Smith"
        assert "_body" in raw.data


# ---------------------------------------------------------------------------
# Transformers
# ---------------------------------------------------------------------------


class TestPersonTransformer:
    def _raw(self, **kwargs) -> RawDocument:
        data = {"name": "Test Person", **kwargs}
        return RawDocument(data=data, source="test.md", object_type="person")

    def test_basic_transform(self):
        transformer = PersonTransformer()
        person = transformer.transform(self._raw(name="Alice", email="alice@example.com"))
        assert isinstance(person, Person)
        assert person.name == "Alice"
        assert person.email == "alice@example.com"

    def test_id_generated_if_missing(self):
        transformer = PersonTransformer()
        person = transformer.transform(self._raw(name="Alice"))
        assert person.id  # auto-generated UUID

    def test_source_file_attached(self):
        transformer = PersonTransformer()
        raw = RawDocument(data={"name": "Alice"}, source="people/alice.md", object_type="person")
        person = transformer.transform(raw)
        assert person.source_file == "people/alice.md"

    def test_tags_parsed(self):
        transformer = PersonTransformer()
        person = transformer.transform(self._raw(tags=["python", "data"]))
        assert person.tags == ["python", "data"]

    def test_tags_string_coerced(self):
        transformer = PersonTransformer()
        person = transformer.transform(self._raw(tags="python"))
        assert person.tags == ["python"]

    def test_missing_name_raises(self):
        transformer = PersonTransformer()
        raw = RawDocument(data={}, source="bad.md", object_type="person")
        with pytest.raises(KeyError):
            transformer.transform(raw)

    def test_transform_many_collects_errors(self):
        transformer = PersonTransformer()
        good = RawDocument(data={"name": "Alice"}, source="alice.md", object_type="person")
        bad = RawDocument(data={}, source="bad.md", object_type="person")
        results, errors = transformer.transform_many([good, bad])
        assert len(results) == 1
        assert len(errors) == 1
        assert "bad.md" in errors[0][0]


class TestCompanyTransformer:
    def test_basic_transform(self):
        transformer = CompanyTransformer()
        raw = RawDocument(
            data={"name": "Acme Corp", "industry": "Tech", "id": "c1"},
            source="acme.md",
            object_type="company",
        )
        company = transformer.transform(raw)
        assert isinstance(company, Company)
        assert company.name == "Acme Corp"
        assert company.industry == "Tech"
        assert company.id == "c1"

    def test_transform_many(self):
        transformer = CompanyTransformer()
        raws = [
            RawDocument(data={"name": "Acme"}, source="acme.md", object_type="company"),
            RawDocument(data={"name": "Beta"}, source="beta.md", object_type="company"),
        ]
        results, errors = transformer.transform_many(raws)
        assert len(results) == 2
        assert len(errors) == 0


class TestProjectTransformer:
    def test_basic_transform(self):
        transformer = ProjectTransformer()
        raw = RawDocument(
            data={"name": "Alpha", "status": "active", "members": ["alice", "bob"]},
            source="alpha.md",
            object_type="project",
        )
        project = transformer.transform(raw)
        assert isinstance(project, Project)
        assert project.status == "active"
        assert "alice" in project.members


# ---------------------------------------------------------------------------
# RepositoryLoader
# ---------------------------------------------------------------------------


class TestRepositoryLoader:
    def test_load_mixed_objects(self):
        people_repo = PeopleRepository()
        companies_repo = CompanyRepository()
        projects_repo = ProjectRepository()
        loader = RepositoryLoader(
            people_repo=people_repo,
            companies_repo=companies_repo,
            projects_repo=projects_repo,
        )
        objects = [
            Person(id="p1", name="Alice"),
            Company(id="c1", name="Acme"),
            Project(id="pr1", name="Alpha"),
        ]
        saved = loader.load(objects)
        assert saved == 3
        assert people_repo.count() == 1
        assert companies_repo.count() == 1
        assert projects_repo.count() == 1

    def test_load_with_missing_repo_skips(self):
        people_repo = PeopleRepository()
        loader = RepositoryLoader(people_repo=people_repo)
        objects = [
            Person(id="p1", name="Alice"),
            Company(id="c1", name="Acme"),  # no companies repo
        ]
        saved = loader.load(objects)
        assert saved == 1

    def test_load_people(self):
        repo = PeopleRepository()
        loader = RepositoryLoader(people_repo=repo)
        count = loader.load_people([Person(id="p1", name="Alice"), Person(id="p2", name="Bob")])
        assert count == 2
        assert repo.count() == 2

    def test_load_companies(self):
        repo = CompanyRepository()
        loader = RepositoryLoader(companies_repo=repo)
        count = loader.load_companies([Company(id="c1", name="Acme")])
        assert count == 1

    def test_load_projects(self):
        repo = ProjectRepository()
        loader = RepositoryLoader(projects_repo=repo)
        count = loader.load_projects([Project(id="pr1", name="Alpha")])
        assert count == 1


# ---------------------------------------------------------------------------
# MarkdownETLPipeline
# ---------------------------------------------------------------------------


class TestMarkdownETLPipeline:
    def _make_pipeline(self, kb_root: Path, object_type=None):
        reader = KnowledgeBaseReader(kb_root)
        loader = RepositoryLoader(
            people_repo=PeopleRepository(),
            companies_repo=CompanyRepository(),
            projects_repo=ProjectRepository(),
        )
        return MarkdownETLPipeline(
            reader=reader,
            loader=loader,
            object_type=object_type,
        )

    def test_run_all_types(self, kb_root: Path):
        pipeline = self._make_pipeline(kb_root)
        result = pipeline.run()
        assert result.records_extracted == 4
        assert result.records_transformed == 4
        assert result.records_loaded == 4
        assert not result.has_errors

    def test_run_people_only(self, kb_root: Path):
        pipeline = self._make_pipeline(kb_root, object_type="person")
        result = pipeline.run()
        assert result.records_extracted == 2
        assert result.records_loaded == 2

    def test_run_company_only(self, kb_root: Path):
        pipeline = self._make_pipeline(kb_root, object_type="company")
        result = pipeline.run()
        assert result.records_extracted == 1
        assert result.records_loaded == 1

    def test_success_rate(self, kb_root: Path):
        pipeline = self._make_pipeline(kb_root)
        result = pipeline.run()
        assert result.success_rate == 1.0

    def test_result_str(self, kb_root: Path):
        pipeline = self._make_pipeline(kb_root)
        result = pipeline.run()
        assert "MarkdownETLPipeline" in str(result)

    def test_error_in_malformed_file(self, tmp_path: Path):
        (tmp_path / "people").mkdir()
        # Missing required 'name' field
        (tmp_path / "people" / "bad.md").write_text(
            textwrap.dedent(
                """\
                ---
                id: bad-001
                email: bad@example.com
                ---
                No name here.
                """
            )
        )
        reader = KnowledgeBaseReader(tmp_path)
        loader = RepositoryLoader(people_repo=PeopleRepository())
        pipeline = MarkdownETLPipeline(reader=reader, loader=loader)
        result = pipeline.run()
        assert result.has_errors
        assert result.records_loaded == 0


class TestETLResult:
    def test_success_rate_zero_extracted(self):
        result = ETLResult(pipeline_name="test")
        assert result.success_rate == 1.0

    def test_has_errors_false(self):
        result = ETLResult(pipeline_name="test")
        assert not result.has_errors

    def test_has_errors_true(self):
        result = ETLResult(pipeline_name="test", errors=[("src", "msg")])
        assert result.has_errors
