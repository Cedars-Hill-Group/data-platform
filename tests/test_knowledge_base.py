"""Tests for the Knowledge Base reader and writer."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from data_platform.knowledge_base.reader import KnowledgeBaseReader, ParsedDocument
from data_platform.knowledge_base.writer import KnowledgeBaseWriter, _slugify
from data_platform.ontology_adapter import TemplateLibrary


class TestKnowledgeBaseReader:
    def test_read_person_file(self, kb_root: Path):
        reader = KnowledgeBaseReader(kb_root)
        doc = reader.read_file(kb_root / "people" / "alice-smith.md")
        assert isinstance(doc, ParsedDocument)
        assert doc.object_type == "person"
        assert doc.metadata["name"] == "Alice Smith"
        assert doc.metadata["email"] == "alice@example.com"
        assert "Alice is a senior engineer" in doc.content

    def test_read_company_file(self, kb_root: Path):
        reader = KnowledgeBaseReader(kb_root)
        doc = reader.read_file(kb_root / "companies" / "acme-corp.md")
        assert doc.object_type == "company"
        assert doc.metadata["name"] == "Acme Corp"

    def test_read_project_file(self, kb_root: Path):
        reader = KnowledgeBaseReader(kb_root)
        doc = reader.read_file(kb_root / "projects" / "project-alpha.md")
        assert doc.object_type == "project"
        assert doc.metadata["status"] == "active"

    def test_read_all_returns_all(self, kb_root: Path):
        reader = KnowledgeBaseReader(kb_root)
        docs = reader.read_all()
        assert len(docs) == 4  # 2 people + 1 company + 1 project

    def test_read_all_filtered_by_type(self, kb_root: Path):
        reader = KnowledgeBaseReader(kb_root)
        people = reader.read_all(object_type="person")
        assert len(people) == 2
        assert all(d.object_type == "person" for d in people)

    def test_list_files(self, kb_root: Path):
        reader = KnowledgeBaseReader(kb_root)
        paths = reader.list_files()
        assert len(paths) == 4

    def test_list_files_filtered(self, kb_root: Path):
        reader = KnowledgeBaseReader(kb_root)
        paths = reader.list_files(object_type="company")
        assert len(paths) == 1

    def test_missing_file_raises(self, kb_root: Path):
        reader = KnowledgeBaseReader(kb_root)
        with pytest.raises(FileNotFoundError):
            reader.read_file(kb_root / "people" / "ghost.md")

    def test_unknown_directory_raises(self, kb_root: Path, tmp_path: Path):
        reader = KnowledgeBaseReader(kb_root)
        # File outside recognised dirs
        orphan = tmp_path / "orphan.md"
        orphan.write_text("---\nname: Orphan\n---\n")
        with pytest.raises(ValueError, match="Cannot determine object type"):
            reader.read_file(orphan)

    def test_empty_kb_returns_empty_list(self, tmp_path: Path):
        reader = KnowledgeBaseReader(tmp_path)
        assert reader.read_all() == []

    def test_repr(self, kb_root: Path):
        reader = KnowledgeBaseReader(kb_root)
        doc = reader.read_file(kb_root / "people" / "alice-smith.md")
        assert "alice-smith.md" in repr(doc)


class TestKnowledgeBaseWriter:
    def test_create_person_file(self, tmp_path: Path):
        writer = KnowledgeBaseWriter(tmp_path)
        path = writer.create("person", name="Charlie Brown", email="charlie@example.com")
        assert path.exists()
        assert path.name == "charlie-brown.md"
        content = path.read_text()
        assert "Charlie Brown" in content

    def test_create_company_file(self, tmp_path: Path):
        writer = KnowledgeBaseWriter(tmp_path)
        path = writer.create("company", name="Delta Corp", industry="Finance")
        assert path.exists()
        content = path.read_text()
        assert "Delta Corp" in content

    def test_create_project_file(self, tmp_path: Path):
        writer = KnowledgeBaseWriter(tmp_path)
        path = writer.create("project", name="Gamma Project", status="planning")
        assert path.exists()

    def test_create_with_explicit_filename(self, tmp_path: Path):
        writer = KnowledgeBaseWriter(tmp_path)
        path = writer.create("person", filename="custom-name", name="Dave")
        assert path.name == "custom-name.md"

    def test_create_raises_if_exists(self, tmp_path: Path):
        writer = KnowledgeBaseWriter(tmp_path)
        writer.create("person", name="Eve")
        with pytest.raises(FileExistsError):
            writer.create("person", name="Eve")

    def test_create_overwrite(self, tmp_path: Path):
        writer = KnowledgeBaseWriter(tmp_path)
        p1 = writer.create("person", name="Eve", email="eve@example.com")
        p2 = writer.create("person", name="Eve", email="eve2@example.com", overwrite=True)
        assert p1 == p2
        assert "eve2@example.com" in p2.read_text()

    def test_update_existing_file(self, kb_root: Path):
        writer = KnowledgeBaseWriter(kb_root)
        alice = kb_root / "people" / "alice-smith.md"
        writer.update(alice, name="Alice Smith", email="alice-new@example.com")
        content = alice.read_text()
        assert "alice-new@example.com" in content

    def test_update_missing_file_raises(self, tmp_path: Path):
        writer = KnowledgeBaseWriter(tmp_path)
        with pytest.raises(FileNotFoundError):
            writer.update(tmp_path / "ghost.md", name="Ghost")

    def test_unknown_object_type_raises(self, tmp_path: Path):
        writer = KnowledgeBaseWriter(tmp_path)
        with pytest.raises(ValueError, match="Unknown object type"):
            writer.create("invoice", name="INV-001")


class TestSluggify:
    def test_basic(self):
        assert _slugify("Alice Smith") == "alice-smith"

    def test_special_chars(self):
        assert _slugify("Acme Corp. (Ltd.)") == "acme-corp-ltd"

    def test_empty_falls_back(self):
        assert _slugify("") == "untitled"

    def test_multiple_spaces(self):
        assert _slugify("  hello   world  ") == "hello-world"


class TestTemplateLibrary:
    def test_get_person_template(self):
        lib = TemplateLibrary()
        tmpl = lib.get_template("person")
        assert "name" in tmpl

    def test_get_unknown_raises(self):
        lib = TemplateLibrary()
        with pytest.raises(KeyError):
            lib.get_template("invoice")

    def test_render_person(self):
        lib = TemplateLibrary()
        rendered = lib.render("person", name="Frank", email="frank@example.com")
        assert "Frank" in rendered
        assert "frank@example.com" in rendered

    def test_available_types(self):
        lib = TemplateLibrary()
        assert set(lib.available_types) == {"person", "company", "project"}
