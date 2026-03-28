"""Tests for Knowledge Base property catalog collection."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

from data_platform.knowledge_base.properties_catalog import (
    collect_property_catalog,
    emit_properties_json,
)


def _make_kb(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    companies = tmp_path / "companies"
    people = tmp_path / "people"
    projects = tmp_path / "Properties"
    companies.mkdir()
    people.mkdir()
    projects.mkdir()

    (companies / "acme.md").write_text(
        textwrap.dedent(
            """\
            ---
            name: Acme Capital
            firm_type: private_equity
            focus:
              - technology
              - healthcare
            ---
            """
        ),
        encoding="utf-8",
    )
    (people / "jane.md").write_text(
        textwrap.dedent(
            """\
            ---
            name: Jane Smith
            firm_type: private_equity
            focus: technology
            ---
            """
        ),
        encoding="utf-8",
    )
    (projects / "project-x.md").write_text(
        textwrap.dedent(
            """\
            ---
            name: Project X
            firm_type: family_office
            focus: data-platform
            ---
            """
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_collect_property_catalog_from_kb(tmp_path: Path) -> None:
    kb_root = _make_kb(tmp_path)
    catalog, saved = collect_property_catalog(kb_root)
    assert saved is None

    firm_type_values = {pv.value for pv in catalog.firm_type}
    focus_values = {pv.value for pv in catalog.focus}

    # Normalisation is snake_case and values are deduplicated.
    assert "technology" in focus_values
    assert "healthcare" in focus_values
    assert "data_platform" in focus_values
    assert "private_equity" in firm_type_values
    assert "family_office" in firm_type_values
    assert len(firm_type_values) == len(set(firm_type_values))
    assert len(focus_values) == len(set(focus_values))


def test_collect_property_catalog_writes_json(tmp_path: Path) -> None:
    kb_root = _make_kb(tmp_path / "kb")
    output_file = tmp_path / "output" / "properties.json"
    catalog, saved = collect_property_catalog(kb_root, output_path=output_file)

    assert saved is not None
    assert saved.exists()
    assert saved.name == "properties.json"

    payload = json.loads(saved.read_text(encoding="utf-8"))
    assert "firm_type" in payload
    assert "focus" in payload

    # File content should match the collected in-memory object shape.
    assert len(payload["firm_type"]) == len(catalog.firm_type)
    assert len(payload["focus"]) == len(catalog.focus)


def test_emit_properties_json(tmp_path: Path) -> None:
    kb_root = _make_kb(tmp_path / "kb")
    output_dir = tmp_path / "output"
    catalog, saved = emit_properties_json(
        knowledge_base_path=kb_root,
        output_dir=output_dir,
    )
    assert saved == (output_dir / "properties.json").resolve()
    assert len(catalog.firm_type) > 0
