"""Tests for the Knowledge Base reader and writer."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from data_platform.knowledge_base.reader import KnowledgeBaseReader, ParsedDocument
from data_platform.knowledge_base.writer import KnowledgeBaseWriter, _slugify
from data_platform.ontology_adapter import TemplateLibrary


@pytest.fixture()
def custom_kb_root(tmp_path: Path) -> Path:
    """Create a minimal KB using non-default folder names."""
    (tmp_path / "staff").mkdir()
    (tmp_path / "orgs").mkdir()
    (tmp_path / "initiatives").mkdir()

    (tmp_path / "staff" / "alice-smith.md").write_text(
        textwrap.dedent(
            """\
            ---
            id: person-001
            name: Alice Smith
            email: alice@example.com
            ---

            Alice is a senior engineer.
            """
        )
    )
    (tmp_path / "orgs" / "acme-corp.md").write_text(
        textwrap.dedent(
            """\
            ---
            id: company-001
            name: Acme Corp
            ---

            Acme Corp builds cloud SaaS products.
            """
        )
    )
    (tmp_path / "initiatives" / "project-alpha.md").write_text(
        textwrap.dedent(
            """\
            ---
            id: project-001
            name: Project Alpha
            status: active
            ---

            The flagship data platform project.
            """
        )
    )
    return tmp_path


_CUSTOM_FOLDER_MAP = {
    "person": "staff",
    "company": "orgs",
    "project": "initiatives",
}


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
        doc = reader.read_file(kb_root / "Properties" / "project-alpha.md")
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


class TestCustomFolderMapReader:
    def test_read_file_with_custom_folders(self, custom_kb_root: Path):
        reader = KnowledgeBaseReader(custom_kb_root, folder_map=_CUSTOM_FOLDER_MAP)
        doc = reader.read_file(custom_kb_root / "staff" / "alice-smith.md")
        assert doc.object_type == "person"
        assert doc.metadata["name"] == "Alice Smith"

    def test_read_all_with_custom_folders(self, custom_kb_root: Path):
        reader = KnowledgeBaseReader(custom_kb_root, folder_map=_CUSTOM_FOLDER_MAP)
        docs = reader.read_all()
        assert len(docs) == 3
        types = {d.object_type for d in docs}
        assert types == {"person", "company", "project"}

    def test_read_all_filtered_with_custom_folders(self, custom_kb_root: Path):
        reader = KnowledgeBaseReader(custom_kb_root, folder_map=_CUSTOM_FOLDER_MAP)
        companies = reader.read_all(object_type="company")
        assert len(companies) == 1
        assert companies[0].metadata["name"] == "Acme Corp"

    def test_list_files_with_custom_folders(self, custom_kb_root: Path):
        reader = KnowledgeBaseReader(custom_kb_root, folder_map=_CUSTOM_FOLDER_MAP)
        paths = reader.list_files()
        assert len(paths) == 3

    def test_list_files_filtered_with_custom_folders(self, custom_kb_root: Path):
        reader = KnowledgeBaseReader(custom_kb_root, folder_map=_CUSTOM_FOLDER_MAP)
        paths = reader.list_files(object_type="project")
        assert len(paths) == 1
        assert paths[0].parent.name == "initiatives"

    def test_default_folder_map_unchanged(self, kb_root: Path):
        """Reader without folder_map still uses the default directory names."""
        reader = KnowledgeBaseReader(kb_root)
        docs = reader.read_all()
        assert len(docs) == 4

    def test_unknown_dir_raises_with_custom_map(self, custom_kb_root: Path, tmp_path: Path):
        reader = KnowledgeBaseReader(custom_kb_root, folder_map=_CUSTOM_FOLDER_MAP)
        orphan = tmp_path / "orphan.md"
        orphan.write_text("---\nname: Orphan\n---\n")
        with pytest.raises(ValueError, match="Cannot determine object type"):
            reader.read_file(orphan)


class TestCustomFolderMapWriter:
    def test_create_with_custom_folders(self, tmp_path: Path):
        writer = KnowledgeBaseWriter(tmp_path, folder_map=_CUSTOM_FOLDER_MAP)
        path = writer.create("person", name="Charlie Brown", email="charlie@example.com")
        assert path.parent.name == "staff"
        assert path.exists()

    def test_create_company_with_custom_folders(self, tmp_path: Path):
        writer = KnowledgeBaseWriter(tmp_path, folder_map=_CUSTOM_FOLDER_MAP)
        path = writer.create("company", name="Delta Corp")
        assert path.parent.name == "orgs"

    def test_create_project_with_custom_folders(self, tmp_path: Path):
        writer = KnowledgeBaseWriter(tmp_path, folder_map=_CUSTOM_FOLDER_MAP)
        path = writer.create("project", name="Omega")
        assert path.parent.name == "initiatives"

    def test_update_with_custom_folders(self, custom_kb_root: Path):
        writer = KnowledgeBaseWriter(custom_kb_root, folder_map=_CUSTOM_FOLDER_MAP)
        alice = custom_kb_root / "staff" / "alice-smith.md"
        writer.update(alice, name="Alice Smith", email="alice-new@example.com")
        assert "alice-new@example.com" in alice.read_text()

    def test_default_folder_map_unchanged(self, tmp_path: Path):
        """Writer without folder_map still writes to default directory names."""
        writer = KnowledgeBaseWriter(tmp_path)
        path = writer.create("person", name="Test User")
        assert path.parent.name == "people"


class TestKnowledgeBaseConfigFolderMap:
    def test_default_folder_map(self):
        from data_platform.config import KnowledgeBaseConfig

        cfg = KnowledgeBaseConfig(path="/tmp/kb")
        assert cfg.folder_map == {
            "person": "people",
            "company": "companies",
            "project": "Properties",
        }

    def test_custom_folder_map(self):
        from data_platform.config import KnowledgeBaseConfig

        cfg = KnowledgeBaseConfig(
            path="/tmp/kb",
            people_folder="staff",
            companies_folder="orgs",
            projects_folder="initiatives",
        )
        assert cfg.folder_map == {
            "person": "staff",
            "company": "orgs",
            "project": "initiatives",
        }

    def test_partial_override(self):
        from data_platform.config import KnowledgeBaseConfig

        cfg = KnowledgeBaseConfig(path="/tmp/kb", people_folder="employees")
        assert cfg.folder_map["person"] == "employees"
        assert cfg.folder_map["company"] == "companies"
        assert cfg.folder_map["project"] == "Properties"

    def test_folder_map_used_by_reader(self, tmp_path: Path):
        from data_platform.config import KnowledgeBaseConfig

        (tmp_path / "staff").mkdir()
        (tmp_path / "staff" / "alice.md").write_text("---\nname: Alice\n---\nHello.")
        cfg = KnowledgeBaseConfig(path=tmp_path, people_folder="staff")
        reader = KnowledgeBaseReader(cfg.path, folder_map=cfg.folder_map)
        docs = reader.read_all(object_type="person")
        assert len(docs) == 1
        assert docs[0].metadata["name"] == "Alice"

    def test_folder_map_used_by_writer(self, tmp_path: Path):
        from data_platform.config import KnowledgeBaseConfig

        cfg = KnowledgeBaseConfig(path=tmp_path, companies_folder="orgs")
        writer = KnowledgeBaseWriter(cfg.path, folder_map=cfg.folder_map)
        path = writer.create("company", name="Test Co")
        assert path.parent.name == "orgs"

    def test_config_yaml_with_custom_folders(self, tmp_path: Path):
        """KnowledgeBaseConfig loads custom folder names from YAML."""
        import yaml
        from data_platform.config import get_config, reset_config_cache

        reset_config_cache()
        kb_path = tmp_path / "kb"
        kb_path.mkdir()
        cfg_data = {
            "knowledge_base": {
                "path": str(kb_path),
                "people_folder": "staff",
                "companies_folder": "orgs",
                "projects_folder": "initiatives",
            },
            "database": {"url": "sqlite:///:memory:"},
            "warehouse": {"type": "none"},
            "object_storage": {"type": "none"},
        }
        p = tmp_path / "config.yaml"
        p.write_text(yaml.dump(cfg_data))
        cfg = get_config(str(p))
        assert cfg.knowledge_base.people_folder == "staff"
        assert cfg.knowledge_base.companies_folder == "orgs"
        assert cfg.knowledge_base.projects_folder == "initiatives"
        assert cfg.knowledge_base.folder_map == {
            "person": "staff",
            "company": "orgs",
            "project": "initiatives",
        }
        reset_config_cache()
