"""Shared pytest fixtures and helpers."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# Temporary Knowledge Base
# ---------------------------------------------------------------------------


@pytest.fixture()
def kb_root(tmp_path: Path) -> Path:
    """Create a minimal markdown Knowledge Base under *tmp_path*."""
    (tmp_path / "people").mkdir()
    (tmp_path / "companies").mkdir()
    (tmp_path / "Properties").mkdir()

    (tmp_path / "people" / "alice-smith.md").write_text(
        textwrap.dedent(
            """\
            ---
            id: person-001
            name: Alice Smith
            email: alice@example.com
            role: Engineer
            organization: Acme Corp
            tags: [python, data]
            ---

            Alice is a senior engineer at Acme Corp.
            """
        )
    )
    (tmp_path / "people" / "bob-jones.md").write_text(
        textwrap.dedent(
            """\
            ---
            id: person-002
            name: Bob Jones
            email: bob@example.com
            role: Manager
            organization: Beta Inc
            tags: [leadership]
            ---

            Bob manages the data team at Beta Inc.
            """
        )
    )
    (tmp_path / "companies" / "acme-corp.md").write_text(
        textwrap.dedent(
            """\
            ---
            id: company-001
            name: Acme Corp
            industry: Technology
            size: Medium
            website: https://acme.example.com
            tags: [saas, cloud]
            ---

            Acme Corp builds cloud SaaS products.
            """
        )
    )
    (tmp_path / "Properties" / "project-alpha.md").write_text(
        textwrap.dedent(
            """\
            ---
            id: project-001
            name: Project Alpha
            status: active
            owner: alice@example.com
            members: [alice@example.com, bob@example.com]
            tags: [data, platform]
            ---

            The flagship data platform project.
            """
        )
    )
    return tmp_path


@pytest.fixture()
def config_file(tmp_path: Path, kb_root: Path) -> Path:
    """Write a minimal config.yaml and return its path."""
    cfg = {
        "knowledge_base": {"path": str(kb_root)},
        "database": {"url": "sqlite:///:memory:", "echo": False},
        "warehouse": {"type": "none"},
        "object_storage": {"type": "none"},
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump(cfg))
    return config_path
