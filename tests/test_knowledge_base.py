"""Tests for the Knowledge Base reader, writer, and manager."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from data_platform.knowledge_base.manager import KnowledgeBaseManager
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
        assert doc.object_type == "property"
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

    def test_read_file_emits_headers_and_sections(self, kb_root: Path):
        profile = kb_root / "people" / "carol-lee.md"
        profile.write_text(
            textwrap.dedent(
                """\
                ---
                id: person-003
                name: Carol Lee
                ---

                # Summary
                Carol is a platform engineer.

                ## Skills
                Python
                Data Engineering

                # Notes
                Prefers async collaboration.
                """
            )
        )
        reader = KnowledgeBaseReader(kb_root)
        doc = reader.read_file(profile)

        assert doc.headers == ["Summary", "Skills", "Notes"]
        assert doc.get_header_content("Summary") == [
            "Carol is a platform engineer.\n\n## Skills\nPython\nData Engineering"
        ]
        assert doc.get_header_content("Skills") == ["Python\nData Engineering"]
        assert doc.get_header_content("Missing") == []

    def test_reader_select_header_content(self, kb_root: Path):
        profile = kb_root / "people" / "dana-park.md"
        profile.write_text(
            textwrap.dedent(
                """\
                ---
                id: person-004
                name: Dana Park
                ---

                # Experience
                Built data ingestion pipelines.

                # Interests
                Mentoring and architecture.
                """
            )
        )
        reader = KnowledgeBaseReader(kb_root)
        selected = reader.select_header_content(profile, ["Interests", "Experience", "Unknown"])

        assert selected == {
            "Interests": ["Mentoring and architecture."],
            "Experience": ["Built data ingestion pipelines."],
            "Unknown": [],
        }

    def test_select_header_content_case_insensitive(self, kb_root: Path):
        profile = kb_root / "people" / "erin-kim.md"
        profile.write_text(
            textwrap.dedent(
                """\
                ---
                id: person-005
                name: Erin Kim
                ---

                # Skills
                SQL and Python.
                """
            )
        )
        reader = KnowledgeBaseReader(kb_root)
        selected = reader.select_header_content(
            profile,
            ["skills"],
            case_sensitive=False,
        )

        assert selected == {"skills": ["SQL and Python."]}

    def test_select_header_content_with_normalization(self, kb_root: Path):
        profile = kb_root / "people" / "finn-ray.md"
        profile.write_text(
            textwrap.dedent(
                """\
                ---
                id: person-006
                name: Finn Ray
                ---

                # Overview:
                Works on reliability.
                """
            )
        )
        reader = KnowledgeBaseReader(kb_root)
        selected = reader.select_header_content(
            profile,
            ["overview"],
            case_sensitive=False,
            normalize=True,
        )

        assert selected == {"overview": ["Works on reliability."]}


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

    def test_write_header_section_updates_existing(self, kb_root: Path):
        writer = KnowledgeBaseWriter(kb_root)
        company = kb_root / "companies" / "acme-corp.md"
        company.write_text(
            textwrap.dedent(
                """\
                ---
                id: company-001
                name: Acme Corp
                ---

                # Overview
                Original overview.

                # Notes
                Existing notes.
                """
            )
        )

        writer.write_header_section(company, "Overview", "Updated overview content.")
        updated = company.read_text()
        assert "Updated overview content." in updated
        assert "Original overview." not in updated
        assert "Existing notes." in updated

    def test_write_header_section_creates_new_header(self, kb_root: Path):
        writer = KnowledgeBaseWriter(kb_root)
        person = kb_root / "people" / "alice-smith.md"

        writer.write_header_section(
            person,
            "Highlights",
            "Leads platform reliability.",
            create_if_missing=True,
            header_level=3,
        )
        updated = person.read_text()
        assert "### Highlights" in updated
        assert "Leads platform reliability." in updated

    def test_write_header_sections_case_insensitive_normalized(self, kb_root: Path):
        writer = KnowledgeBaseWriter(kb_root)
        person = kb_root / "people" / "bob-jones.md"
        person.write_text(
            textwrap.dedent(
                """\
                ---
                id: person-002
                name: Bob Jones
                ---

                # Profile:
                Old profile text.
                """
            )
        )

        writer.write_header_sections(
            person,
            {"profile": "New profile text."},
            case_sensitive=False,
            normalize=True,
        )
        updated = person.read_text()
        assert "New profile text." in updated
        assert "Old profile text." not in updated

    def test_write_header_section_missing_header_without_create_raises(self, kb_root: Path):
        writer = KnowledgeBaseWriter(kb_root)
        person = kb_root / "people" / "alice-smith.md"

        with pytest.raises(ValueError, match="Header not found"):
            writer.write_header_section(
                person,
                "Does Not Exist",
                "text",
                create_if_missing=False,
            )

    def test_append_header_section_appends_existing_content(self, kb_root: Path):
        writer = KnowledgeBaseWriter(kb_root)
        company = kb_root / "companies" / "acme-corp.md"
        company.write_text(
            textwrap.dedent(
                """\
                ---
                id: company-001
                name: Acme Corp
                ---

                # Notes
                Existing note.
                """
            )
        )

        writer.append_header_section(company, "Notes", "Second note.")
        updated = company.read_text()
        assert "Existing note." in updated
        assert "Second note." in updated
        assert updated.index("Existing note.") < updated.index("Second note.")

    def test_append_header_section_creates_when_missing(self, kb_root: Path):
        writer = KnowledgeBaseWriter(kb_root)
        person = kb_root / "people" / "alice-smith.md"

        writer.append_header_section(
            person,
            "Activity",
            "Presented at architecture review.",
            create_if_missing=True,
            header_level=3,
        )
        updated = person.read_text()
        assert "### Activity" in updated
        assert "Presented at architecture review." in updated

    def test_append_header_section_missing_without_create_raises(self, kb_root: Path):
        writer = KnowledgeBaseWriter(kb_root)
        person = kb_root / "people" / "bob-jones.md"

        with pytest.raises(ValueError, match="Header not found"):
            writer.append_header_section(
                person,
                "Nope",
                "Text",
                create_if_missing=False,
            )


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
        # "property" is the canonical type; "project" is retained as a backward-compatible alias.
        assert set(lib.available_types) == {"person", "company", "property", "project"}


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


class TestKnowledgeBaseWriterDelete:
    def test_delete_existing_file(self, kb_root: Path):
        writer = KnowledgeBaseWriter(kb_root)
        alice = kb_root / "people" / "alice-smith.md"
        assert alice.exists()
        writer.delete(alice)
        assert not alice.exists()

    def test_delete_missing_file_raises(self, tmp_path: Path):
        writer = KnowledgeBaseWriter(tmp_path)
        with pytest.raises(FileNotFoundError):
            writer.delete(tmp_path / "ghost.md")


class TestKnowledgeBaseManager:
    def test_read_file(self, kb_root: Path):
        manager = KnowledgeBaseManager(kb_root)
        doc = manager.read_file(kb_root / "people" / "alice-smith.md")
        assert isinstance(doc, ParsedDocument)
        assert doc.object_type == "person"
        assert doc.metadata["name"] == "Alice Smith"

    def test_read_all(self, kb_root: Path):
        manager = KnowledgeBaseManager(kb_root)
        docs = manager.read_all()
        assert len(docs) == 4

    def test_read_all_filtered(self, kb_root: Path):
        manager = KnowledgeBaseManager(kb_root)
        people = manager.read_all(object_type="person")
        assert len(people) == 2
        assert all(d.object_type == "person" for d in people)

    def test_list_files(self, kb_root: Path):
        manager = KnowledgeBaseManager(kb_root)
        paths = manager.list_files()
        assert len(paths) == 4

    def test_list_files_filtered(self, kb_root: Path):
        manager = KnowledgeBaseManager(kb_root)
        paths = manager.list_files(object_type="company")
        assert len(paths) == 1

    def test_select_header_content(self, kb_root: Path):
        profile = kb_root / "people" / "mgr-test.md"
        profile.write_text(
            textwrap.dedent(
                """\
                ---
                id: person-mgr
                name: Mgr Test
                ---

                # Skills
                Python
                """
            )
        )
        manager = KnowledgeBaseManager(kb_root)
        selected = manager.select_header_content(profile, ["Skills"])
        assert selected == {"Skills": ["Python"]}

    def test_create(self, tmp_path: Path):
        manager = KnowledgeBaseManager(tmp_path)
        path = manager.create("person", name="New Person", email="new@example.com")
        assert path.exists()
        assert "New Person" in path.read_text()

    def test_create_raises_if_exists(self, tmp_path: Path):
        manager = KnowledgeBaseManager(tmp_path)
        manager.create("person", name="Dup")
        with pytest.raises(FileExistsError):
            manager.create("person", name="Dup")

    def test_update(self, kb_root: Path):
        manager = KnowledgeBaseManager(kb_root)
        alice = kb_root / "people" / "alice-smith.md"
        manager.update(alice, email="updated@example.com")
        assert "updated@example.com" in alice.read_text()

    def test_update_missing_raises(self, tmp_path: Path):
        manager = KnowledgeBaseManager(tmp_path)
        with pytest.raises(FileNotFoundError):
            manager.update(tmp_path / "ghost.md", name="Ghost")

    def test_write_header_section(self, kb_root: Path):
        manager = KnowledgeBaseManager(kb_root)
        company = kb_root / "companies" / "acme-corp.md"
        company.write_text(
            textwrap.dedent(
                """\
                ---
                id: company-001
                name: Acme Corp
                ---

                # Overview
                Old text.
                """
            )
        )
        manager.write_header_section(company, "Overview", "New text.")
        assert "New text." in company.read_text()
        assert "Old text." not in company.read_text()

    def test_write_header_sections(self, kb_root: Path):
        manager = KnowledgeBaseManager(kb_root)
        company = kb_root / "companies" / "acme-corp.md"
        company.write_text(
            textwrap.dedent(
                """\
                ---
                id: company-001
                name: Acme Corp
                ---

                # Overview
                Original overview.

                # Notes
                Original notes.
                """
            )
        )
        manager.write_header_sections(company, {"Overview": "Updated overview.", "Notes": "Updated notes."})
        updated = company.read_text()
        assert "Updated overview." in updated
        assert "Updated notes." in updated
        assert "Original overview." not in updated

    def test_append_header_section(self, kb_root: Path):
        manager = KnowledgeBaseManager(kb_root)
        person = kb_root / "people" / "alice-smith.md"
        person.write_text(
            textwrap.dedent(
                """\
                ---
                id: person-001
                name: Alice Smith
                ---

                # Notes
                First note.
                """
            )
        )
        manager.append_header_section(person, "Notes", "Second note.")
        updated = person.read_text()
        assert "First note." in updated
        assert "Second note." in updated

    def test_append_header_sections(self, kb_root: Path):
        manager = KnowledgeBaseManager(kb_root)
        person = kb_root / "people" / "alice-smith.md"
        person.write_text(
            textwrap.dedent(
                """\
                ---
                id: person-001
                name: Alice Smith
                ---

                # Activity
                Joined Q1.
                """
            )
        )
        manager.append_header_sections(person, {"Activity": "Promoted Q3."})
        updated = person.read_text()
        assert "Joined Q1." in updated
        assert "Promoted Q3." in updated

    def test_delete(self, kb_root: Path):
        manager = KnowledgeBaseManager(kb_root)
        alice = kb_root / "people" / "alice-smith.md"
        assert alice.exists()
        manager.delete(alice)
        assert not alice.exists()

    def test_delete_missing_raises(self, tmp_path: Path):
        manager = KnowledgeBaseManager(tmp_path)
        with pytest.raises(FileNotFoundError):
            manager.delete(tmp_path / "ghost.md")

    def test_root_property(self, kb_root: Path):
        manager = KnowledgeBaseManager(kb_root)
        assert manager.root == kb_root

    def test_custom_folder_map(self, custom_kb_root: Path):
        manager = KnowledgeBaseManager(custom_kb_root, folder_map=_CUSTOM_FOLDER_MAP)
        docs = manager.read_all()
        assert len(docs) == 3

    def test_create_and_delete_full_lifecycle(self, tmp_path: Path):
        manager = KnowledgeBaseManager(tmp_path)
        path = manager.create("company", name="Lifecycle Corp")
        assert path.exists()
        manager.update(path, industry="Technology")
        manager.write_header_section(path, "Overview", "A technology company.")
        doc = manager.read_file(path)
        assert doc.metadata.get("industry") == "Technology"
        assert doc.get_header_content("Overview") == ["A technology company."]
        manager.delete(path)
        assert not path.exists()
