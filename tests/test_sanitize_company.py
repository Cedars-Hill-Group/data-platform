"""Tests for the CompanySanitizer action tool."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import frontmatter
import pytest

from data_platform._stubs.catalogs import (
    DEFAULT_ATTRIBUTES_CATALOG,
    DEFAULT_NAICS_CATALOG,
    AttributesCatalog,
    CatalogProperty,
    CatalogPropertyValue,
    NaicsCatalog,
    NaicsEntry,
)
from data_platform.actions.sanitize_company import CompanySanitizer, SanitizeResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_llm(responses: list[str]) -> MagicMock:
    """Return a mock LLMClient whose chat() yields *responses* in order."""
    client = MagicMock()
    client.chat.side_effect = responses
    return client


def _make_company_file(directory: Path, filename: str, metadata: dict[str, Any], body: str) -> Path:
    """Write a company markdown file and return its path."""
    post = frontmatter.Post(body, **metadata)
    path = directory / filename
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def companies_dir(tmp_path: Path) -> Path:
    d = tmp_path / "companies"
    d.mkdir()
    return d


@pytest.fixture()
def kb_root(companies_dir: Path) -> Path:
    return companies_dir.parent


@pytest.fixture()
def simple_company(companies_dir: Path) -> Path:
    return _make_company_file(
        companies_dir,
        "acme.md",
        {"name": "Acme Capital", "firm_type": "pe", "focus": ["tech"]},
        "Acme Capital is a private equity firm focused on technology buyouts.",
    )


@pytest.fixture()
def no_website_company(companies_dir: Path) -> Path:
    return _make_company_file(
        companies_dir,
        "beta.md",
        {"name": "Beta Ventures", "focus": ["healthcare"]},
        "Beta Ventures is a healthcare-focused venture capital firm.",
    )


@pytest.fixture()
def minimal_catalog() -> AttributesCatalog:
    return AttributesCatalog(
        properties=[
            CatalogProperty(
                field="firm_type",
                description="Type of investment firm.",
                accept_multiple_values=False,
                values=[
                    CatalogPropertyValue(value="private_equity", description="PE firm."),
                    CatalogPropertyValue(value="venture_capital", description="VC firm."),
                ],
            ),
            CatalogProperty(
                field="focus",
                description="Investment focus areas.",
                accept_multiple_values=True,
                values=[
                    CatalogPropertyValue(value="technology", description="Tech sector."),
                    CatalogPropertyValue(value="healthcare", description="Healthcare sector."),
                ],
            ),
        ]
    )


@pytest.fixture()
def minimal_naics() -> NaicsCatalog:
    return NaicsCatalog(
        sectors=[
            NaicsEntry(code="52", title="Finance and Insurance"),
            NaicsEntry(code="51", title="Information"),
        ]
    )


# ---------------------------------------------------------------------------
# SanitizeResult
# ---------------------------------------------------------------------------


class TestSanitizeResult:
    def test_success_when_no_error(self):
        result = SanitizeResult(Path("x.md"), {"firm_type": "private_equity"})
        assert result.success is True
        assert result.error is None

    def test_failure_when_error_set(self):
        result = SanitizeResult(Path("x.md"), {}, error="oops")
        assert result.success is False
        assert result.error == "oops"

    def test_repr(self):
        r = SanitizeResult(Path("foo.md"), {"a": 1, "b": 2})
        assert "foo.md" in repr(r)
        assert "['a', 'b']" in repr(r)


# ---------------------------------------------------------------------------
# CompanySanitizer – _normalize_properties
# ---------------------------------------------------------------------------


class TestNormalizeProperties:
    def test_single_value_field(
        self,
        kb_root: Path,
        simple_company: Path,
        minimal_catalog: AttributesCatalog,
        minimal_naics: NaicsCatalog,
    ):
        # firm_type → single value; focus → multiple values
        llm = _make_llm([
            '["private_equity"]',      # firm_type
            '["technology"]',          # focus
        ])
        sanitizer = CompanySanitizer(
            kb_root, llm, minimal_catalog, minimal_naics, dry_run=True
        )
        from data_platform.knowledge_base.reader import KnowledgeBaseReader
        reader = KnowledgeBaseReader(kb_root, folder_map={"company": "companies"})
        doc = reader.read_file(simple_company)
        changes = sanitizer._normalize_properties(doc)

        assert changes["firm_type"] == "private_equity"
        assert changes["focus"] == ["technology"]

    def test_multiple_values_field(
        self,
        kb_root: Path,
        simple_company: Path,
        minimal_catalog: AttributesCatalog,
        minimal_naics: NaicsCatalog,
    ):
        llm = _make_llm([
            '["private_equity"]',
            '["technology", "healthcare"]',
        ])
        sanitizer = CompanySanitizer(
            kb_root, llm, minimal_catalog, minimal_naics, dry_run=True
        )
        from data_platform.knowledge_base.reader import KnowledgeBaseReader
        reader = KnowledgeBaseReader(kb_root, folder_map={"company": "companies"})
        doc = reader.read_file(simple_company)
        changes = sanitizer._normalize_properties(doc)
        assert changes["focus"] == ["technology", "healthcare"]

    def test_empty_llm_response_skips_field(
        self,
        kb_root: Path,
        simple_company: Path,
        minimal_catalog: AttributesCatalog,
        minimal_naics: NaicsCatalog,
    ):
        llm = _make_llm(["[]", "[]"])
        sanitizer = CompanySanitizer(
            kb_root, llm, minimal_catalog, minimal_naics, dry_run=True
        )
        from data_platform.knowledge_base.reader import KnowledgeBaseReader
        reader = KnowledgeBaseReader(kb_root, folder_map={"company": "companies"})
        doc = reader.read_file(simple_company)
        changes = sanitizer._normalize_properties(doc)
        # Empty lists → no change stored for either field
        assert "firm_type" not in changes
        assert "focus" not in changes

    def test_invalid_json_response_skips_field(
        self,
        kb_root: Path,
        simple_company: Path,
        minimal_catalog: AttributesCatalog,
        minimal_naics: NaicsCatalog,
    ):
        llm = _make_llm(["not valid json", "[]"])
        sanitizer = CompanySanitizer(
            kb_root, llm, minimal_catalog, minimal_naics, dry_run=True
        )
        from data_platform.knowledge_base.reader import KnowledgeBaseReader
        reader = KnowledgeBaseReader(kb_root, folder_map={"company": "companies"})
        doc = reader.read_file(simple_company)
        changes = sanitizer._normalize_properties(doc)
        assert "firm_type" not in changes


# ---------------------------------------------------------------------------
# CompanySanitizer – _ensure_website
# ---------------------------------------------------------------------------


class TestEnsureWebsite:
    def test_skips_if_website_present(
        self,
        kb_root: Path,
        companies_dir: Path,
        minimal_catalog: AttributesCatalog,
        minimal_naics: NaicsCatalog,
    ):
        path = _make_company_file(
            companies_dir, "has_website.md",
            {"name": "Corp", "website": "https://corp.example.com"},
            "Corp is a company.",
        )
        llm = _make_llm([])
        sanitizer = CompanySanitizer(
            kb_root, llm, minimal_catalog, minimal_naics, dry_run=True
        )
        from data_platform.knowledge_base.reader import KnowledgeBaseReader
        reader = KnowledgeBaseReader(kb_root, folder_map={"company": "companies"})
        doc = reader.read_file(path)
        changes = sanitizer._ensure_website(doc)
        assert changes == {}
        llm.chat.assert_not_called()

    def test_adds_website_when_missing(
        self,
        kb_root: Path,
        no_website_company: Path,
        minimal_catalog: AttributesCatalog,
        minimal_naics: NaicsCatalog,
    ):
        llm = _make_llm(["https://betaventures.example.com"])
        sanitizer = CompanySanitizer(
            kb_root, llm, minimal_catalog, minimal_naics, dry_run=True
        )
        from data_platform.knowledge_base.reader import KnowledgeBaseReader
        reader = KnowledgeBaseReader(kb_root, folder_map={"company": "companies"})
        doc = reader.read_file(no_website_company)
        changes = sanitizer._ensure_website(doc)
        assert changes == {"website": "https://betaventures.example.com"}

    def test_null_response_returns_empty(
        self,
        kb_root: Path,
        no_website_company: Path,
        minimal_catalog: AttributesCatalog,
        minimal_naics: NaicsCatalog,
    ):
        llm = _make_llm(["null"])
        sanitizer = CompanySanitizer(
            kb_root, llm, minimal_catalog, minimal_naics, dry_run=True
        )
        from data_platform.knowledge_base.reader import KnowledgeBaseReader
        reader = KnowledgeBaseReader(kb_root, folder_map={"company": "companies"})
        doc = reader.read_file(no_website_company)
        changes = sanitizer._ensure_website(doc)
        assert changes == {}

    def test_non_http_response_returns_empty(
        self,
        kb_root: Path,
        no_website_company: Path,
        minimal_catalog: AttributesCatalog,
        minimal_naics: NaicsCatalog,
    ):
        llm = _make_llm(["www.example.com"])  # missing scheme
        sanitizer = CompanySanitizer(
            kb_root, llm, minimal_catalog, minimal_naics, dry_run=True
        )
        from data_platform.knowledge_base.reader import KnowledgeBaseReader
        reader = KnowledgeBaseReader(kb_root, folder_map={"company": "companies"})
        doc = reader.read_file(no_website_company)
        changes = sanitizer._ensure_website(doc)
        assert changes == {}


# ---------------------------------------------------------------------------
# CompanySanitizer – _classify_naics
# ---------------------------------------------------------------------------


class TestClassifyNaics:
    def test_classifies_company(
        self,
        kb_root: Path,
        simple_company: Path,
        minimal_catalog: AttributesCatalog,
        minimal_naics: NaicsCatalog,
    ):
        naics_response = json.dumps({
            "naics_sector_code": "52",
            "naics_sector_title": "Finance and Insurance",
            "naics_code": "5231",
            "naics_title": "Securities and Commodity Contracts",
        })
        llm = _make_llm([naics_response])
        sanitizer = CompanySanitizer(
            kb_root, llm, minimal_catalog, minimal_naics, dry_run=True
        )
        from data_platform.knowledge_base.reader import KnowledgeBaseReader
        reader = KnowledgeBaseReader(kb_root, folder_map={"company": "companies"})
        doc = reader.read_file(simple_company)
        changes = sanitizer._classify_naics(doc)

        assert changes["naics_sector_code"] == "52"
        assert changes["naics_code"] == "5231"

    def test_invalid_json_returns_empty(
        self,
        kb_root: Path,
        simple_company: Path,
        minimal_catalog: AttributesCatalog,
        minimal_naics: NaicsCatalog,
    ):
        llm = _make_llm(["not-json"])
        sanitizer = CompanySanitizer(
            kb_root, llm, minimal_catalog, minimal_naics, dry_run=True
        )
        from data_platform.knowledge_base.reader import KnowledgeBaseReader
        reader = KnowledgeBaseReader(kb_root, folder_map={"company": "companies"})
        doc = reader.read_file(simple_company)
        changes = sanitizer._classify_naics(doc)
        assert changes == {}


# ---------------------------------------------------------------------------
# CompanySanitizer – sanitize_file (integration)
# ---------------------------------------------------------------------------


class TestSanitizeFile:
    def _make_responses(self) -> list[str]:
        """Returns a list of LLM responses covering normalize + website + naics."""
        return [
            '["private_equity"]',        # firm_type normalization
            '["technology"]',             # focus normalization
            "https://acme.example.com",   # website agent
            json.dumps({                  # NAICS
                "naics_sector_code": "52",
                "naics_sector_title": "Finance and Insurance",
                "naics_code": "5231",
                "naics_title": "Securities and Commodity Contracts",
            }),
        ]

    def test_dry_run_no_file_changes(
        self,
        kb_root: Path,
        simple_company: Path,
        minimal_catalog: AttributesCatalog,
        minimal_naics: NaicsCatalog,
    ):
        original = simple_company.read_text(encoding="utf-8")
        llm = _make_llm(self._make_responses())
        sanitizer = CompanySanitizer(
            kb_root, llm, minimal_catalog, minimal_naics, dry_run=True
        )
        result = sanitizer.sanitize_file(simple_company)
        # File must be untouched in dry-run mode.
        assert simple_company.read_text(encoding="utf-8") == original
        assert result.success is True
        assert "firm_type" in result.changes

    def test_writes_changes_when_not_dry_run(
        self,
        kb_root: Path,
        no_website_company: Path,
        minimal_catalog: AttributesCatalog,
        minimal_naics: NaicsCatalog,
    ):
        llm = _make_llm([
            '["venture_capital"]',
            '["healthcare"]',
            "https://beta.example.com",
            json.dumps({
                "naics_sector_code": "62",
                "naics_sector_title": "Health Care and Social Assistance",
                "naics_code": "6211",
                "naics_title": "Offices of Physicians",
            }),
        ])
        sanitizer = CompanySanitizer(
            kb_root, llm, minimal_catalog, minimal_naics, dry_run=False
        )
        result = sanitizer.sanitize_file(no_website_company)
        assert result.success is True

        # Verify file was actually updated.
        post = frontmatter.load(str(no_website_company))
        assert post.metadata.get("website") == "https://beta.example.com"
        assert post.metadata.get("firm_type") == "venture_capital"
        assert post.metadata.get("naics_code") == "6211"

    def test_file_not_found_returns_error_result(
        self,
        kb_root: Path,
        minimal_catalog: AttributesCatalog,
        minimal_naics: NaicsCatalog,
    ):
        llm = _make_llm([])
        sanitizer = CompanySanitizer(
            kb_root, llm, minimal_catalog, minimal_naics, dry_run=True
        )
        result = sanitizer.sanitize_file(kb_root / "companies" / "ghost.md")
        assert result.success is False
        assert result.error is not None

    def test_body_text_limit_truncates(
        self,
        kb_root: Path,
        companies_dir: Path,
        minimal_catalog: AttributesCatalog,
        minimal_naics: NaicsCatalog,
    ):
        long_body = "x" * 10_000
        path = _make_company_file(
            companies_dir, "long.md",
            {"name": "Long Corp"},
            long_body,
        )
        llm = _make_llm([
            '["private_equity"]',
            '["technology"]',
            "https://long.example.com",
            json.dumps({"naics_sector_code": "51", "naics_sector_title": "Information",
                        "naics_code": "5112", "naics_title": "Software Publishers"}),
        ])
        sanitizer = CompanySanitizer(
            kb_root, llm, minimal_catalog, minimal_naics,
            dry_run=True, body_text_limit=100,
        )
        sanitizer.sanitize_file(path)
        # Check that the user prompts sent to LLM don't contain the full 10k body.
        for call_args in llm.chat.call_args_list:
            user_text = call_args.kwargs.get("user", "") or call_args.args[1] if call_args.args else ""
            assert len(user_text) < 5000, "user prompt should be truncated"


# ---------------------------------------------------------------------------
# CompanySanitizer – sanitize_all
# ---------------------------------------------------------------------------


class TestSanitizeAll:
    def test_processes_all_company_files(
        self,
        kb_root: Path,
        companies_dir: Path,
        minimal_catalog: AttributesCatalog,
        minimal_naics: NaicsCatalog,
    ):
        _make_company_file(companies_dir, "co1.md", {"name": "Co1"}, "Co1 description.")
        _make_company_file(companies_dir, "co2.md", {"name": "Co2"}, "Co2 description.")

        # 4 LLM calls per file × 2 files = 8 calls total
        # (2 for normalisation + 1 website + 1 naics each)
        per_file_responses = [
            '["private_equity"]',
            '["technology"]',
            "https://co.example.com",
            json.dumps({"naics_sector_code": "52", "naics_sector_title": "Finance",
                        "naics_code": "5231", "naics_title": "Securities"}),
        ]
        llm = _make_llm(per_file_responses * 2)
        sanitizer = CompanySanitizer(
            kb_root, llm, minimal_catalog, minimal_naics, dry_run=True
        )
        results = sanitizer.sanitize_all()
        assert len(results) == 2
        assert all(r.success for r in results)

    def test_empty_kb_returns_empty_list(
        self,
        kb_root: Path,
        minimal_catalog: AttributesCatalog,
        minimal_naics: NaicsCatalog,
    ):
        llm = _make_llm([])
        sanitizer = CompanySanitizer(
            kb_root, llm, minimal_catalog, minimal_naics, dry_run=True
        )
        results = sanitizer.sanitize_all()
        assert results == []


# ---------------------------------------------------------------------------
# Default catalog stubs
# ---------------------------------------------------------------------------


class TestDefaultCatalogs:
    def test_default_attributes_catalog_has_firm_type_and_focus(self):
        fields = {p.field for p in DEFAULT_ATTRIBUTES_CATALOG.properties}
        assert "firm_type" in fields
        assert "focus" in fields

    def test_focus_accepts_multiple_values(self):
        focus_prop = DEFAULT_ATTRIBUTES_CATALOG.get_property("focus")
        assert focus_prop is not None
        assert focus_prop.accept_multiple_values is True

    def test_firm_type_does_not_accept_multiple_values(self):
        ft_prop = DEFAULT_ATTRIBUTES_CATALOG.get_property("firm_type")
        assert ft_prop is not None
        assert ft_prop.accept_multiple_values is False

    def test_default_naics_has_sectors(self):
        assert len(DEFAULT_NAICS_CATALOG.sectors) > 0

    def test_naics_get_sector(self):
        sector = DEFAULT_NAICS_CATALOG.get_sector("52")
        assert sector is not None
        assert "Finance" in sector.title

    def test_attributes_catalog_load_json(self, tmp_path: Path):
        data = {
            "properties": [
                {
                    "field": "my_field",
                    "description": "Test field.",
                    "accept_multiple_values": True,
                    "values": [
                        {"value": "a", "description": "Option A"},
                    ],
                }
            ]
        }
        path = tmp_path / "attrs.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        catalog = AttributesCatalog.load_json(path)
        assert len(catalog.properties) == 1
        assert catalog.get_property("my_field") is not None

    def test_naics_catalog_load_json(self, tmp_path: Path):
        data = {
            "sectors": [
                {"code": "11", "title": "Agriculture"},
            ]
        }
        path = tmp_path / "naics.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        catalog = NaicsCatalog.load_json(path)
        assert len(catalog.sectors) == 1
        assert catalog.sectors[0].code == "11"
