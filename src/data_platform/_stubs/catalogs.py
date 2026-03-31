"""
Stub implementations of the ontology-core catalog types.

These stubs mirror the public interface expected from the ``ontology_core``
library for the ``attributes.json`` and ``naics.json`` catalogs.

They are used automatically when ``ontology_core`` is not installed.

When ``ontology_core`` *is* installed, the real implementations take
precedence via :mod:`data_platform.ontology_adapter`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Attributes / Properties catalog
# ---------------------------------------------------------------------------


class CatalogPropertyValue(BaseModel):
    """A single allowed value for a cataloged metadata property."""

    value: str = Field(..., description="Normalised value identifier.")
    description: str = Field(..., description="Human-readable description of this value.")


class CatalogProperty(BaseModel):
    """Describes a metadata property, its allowed values, and cardinality."""

    field: str = Field(..., description="Metadata field name (e.g. 'firm_type').")
    description: str = Field(..., description="Human-readable description of the property.")
    accept_multiple_values: bool = Field(
        False,
        description="Whether the field may hold multiple values.",
    )
    values: list[CatalogPropertyValue] = Field(default_factory=list)


class AttributesCatalog(BaseModel):
    """Catalog of metadata properties with their allowed values."""

    properties: list[CatalogProperty] = Field(default_factory=list)

    def get_property(self, field: str) -> CatalogProperty | None:
        """Return the :class:`CatalogProperty` for *field*, or *None*."""
        for prop in self.properties:
            if prop.field == field:
                return prop
        return None

    @classmethod
    def load_json(cls, path: str | Path) -> AttributesCatalog:
        """Load a catalog from a JSON file on disk."""
        raw: Any = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.model_validate(raw)


# ---------------------------------------------------------------------------
# NAICS catalog
# ---------------------------------------------------------------------------


class NaicsEntry(BaseModel):
    """One node in the NAICS hierarchy (sector, subsector, industry group, …)."""

    code: str = Field(..., description="NAICS code.")
    title: str = Field(..., description="Title of this classification level.")
    description: str = Field("", description="Optional extended description.")
    subsectors: list[NaicsEntry] = Field(default_factory=list)


class NaicsCatalog(BaseModel):
    """Full NAICS hierarchy, keyed by top-level sectors."""

    sectors: list[NaicsEntry] = Field(default_factory=list)

    def get_sector(self, code: str) -> NaicsEntry | None:
        """Return the sector whose code matches *code*, or *None*."""
        for sector in self.sectors:
            if sector.code == code:
                return sector
        return None

    @classmethod
    def load_json(cls, path: str | Path) -> NaicsCatalog:
        """Load a NAICS catalog from a JSON file on disk."""
        raw: Any = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.model_validate(raw)


# ---------------------------------------------------------------------------
# Default stub instances
# ---------------------------------------------------------------------------

#: Default attributes catalog used when ontology-core is not installed.
DEFAULT_ATTRIBUTES_CATALOG = AttributesCatalog(
    properties=[
        CatalogProperty(
            field="firm_type",
            description="The type of investment firm or fund structure.",
            accept_multiple_values=False,
            values=[
                CatalogPropertyValue(
                    value="private_equity",
                    description=(
                        "A firm that invests in private companies using capital raised from "
                        "institutional and accredited investors, typically seeking majority control."
                    ),
                ),
                CatalogPropertyValue(
                    value="venture_capital",
                    description=(
                        "A firm that provides early-stage funding to startups and high-growth "
                        "companies in exchange for equity."
                    ),
                ),
                CatalogPropertyValue(
                    value="growth_equity",
                    description=(
                        "A firm that invests in relatively mature companies seeking capital to "
                        "expand operations without a change of control."
                    ),
                ),
                CatalogPropertyValue(
                    value="family_office",
                    description=(
                        "A privately held company that manages investments and wealth for a "
                        "single ultra-high-net-worth family."
                    ),
                ),
                CatalogPropertyValue(
                    value="hedge_fund",
                    description=(
                        "A pooled investment fund that employs different strategies to earn "
                        "active returns for its investors."
                    ),
                ),
                CatalogPropertyValue(
                    value="real_estate",
                    description=(
                        "A firm focused primarily on real estate investments, including "
                        "commercial, residential, or industrial properties."
                    ),
                ),
                CatalogPropertyValue(
                    value="corporate",
                    description=(
                        "An operating company rather than an investment vehicle; "
                        "typically a strategic acquirer or operating business."
                    ),
                ),
                CatalogPropertyValue(
                    value="other",
                    description=(
                        "Any other type of firm not covered by the categories above."
                    ),
                ),
            ],
        ),
        CatalogProperty(
            field="focus",
            description="Primary investment focus areas, sectors, or themes.",
            accept_multiple_values=True,
            values=[
                CatalogPropertyValue(
                    value="technology",
                    description=(
                        "Software, hardware, semiconductors, IT services, and other "
                        "technology-oriented companies."
                    ),
                ),
                CatalogPropertyValue(
                    value="healthcare",
                    description=(
                        "Pharmaceuticals, medical devices, healthcare services, biotech, "
                        "and life sciences."
                    ),
                ),
                CatalogPropertyValue(
                    value="financial_services",
                    description=(
                        "Banks, insurance, fintech, asset management, and other "
                        "financial-industry companies."
                    ),
                ),
                CatalogPropertyValue(
                    value="consumer",
                    description=(
                        "Consumer goods, retail, food and beverage, and branded consumer "
                        "products or services."
                    ),
                ),
                CatalogPropertyValue(
                    value="industrials",
                    description=(
                        "Manufacturing, logistics, aerospace, defense, and other industrial "
                        "businesses."
                    ),
                ),
                CatalogPropertyValue(
                    value="energy",
                    description=(
                        "Oil and gas, utilities, renewable energy, and energy infrastructure."
                    ),
                ),
                CatalogPropertyValue(
                    value="real_estate",
                    description=(
                        "Commercial, residential, and industrial real estate assets and "
                        "related services."
                    ),
                ),
                CatalogPropertyValue(
                    value="media_entertainment",
                    description=(
                        "Media, entertainment, sports, gaming, and content businesses."
                    ),
                ),
                CatalogPropertyValue(
                    value="education",
                    description=(
                        "Educational institutions, edtech, training, and learning platforms."
                    ),
                ),
                CatalogPropertyValue(
                    value="business_services",
                    description=(
                        "Professional services, outsourcing, staffing, and B2B service "
                        "businesses."
                    ),
                ),
            ],
        ),
    ]
)


#: Default NAICS catalog (top-level sectors only) used when ontology-core is not installed.
DEFAULT_NAICS_CATALOG = NaicsCatalog(
    sectors=[
        NaicsEntry(code="11", title="Agriculture, Forestry, Fishing and Hunting"),
        NaicsEntry(code="21", title="Mining, Quarrying, and Oil and Gas Extraction"),
        NaicsEntry(code="22", title="Utilities"),
        NaicsEntry(code="23", title="Construction"),
        NaicsEntry(
            code="31-33",
            title="Manufacturing",
        ),
        NaicsEntry(code="42", title="Wholesale Trade"),
        NaicsEntry(code="44-45", title="Retail Trade"),
        NaicsEntry(
            code="48-49",
            title="Transportation and Warehousing",
        ),
        NaicsEntry(code="51", title="Information"),
        NaicsEntry(code="52", title="Finance and Insurance"),
        NaicsEntry(code="53", title="Real Estate and Rental and Leasing"),
        NaicsEntry(
            code="54",
            title="Professional, Scientific, and Technical Services",
        ),
        NaicsEntry(
            code="55",
            title="Management of Companies and Enterprises",
        ),
        NaicsEntry(
            code="56",
            title=(
                "Administrative and Support and Waste Management and Remediation Services"
            ),
        ),
        NaicsEntry(code="61", title="Educational Services"),
        NaicsEntry(code="62", title="Health Care and Social Assistance"),
        NaicsEntry(
            code="71",
            title="Arts, Entertainment, and Recreation",
        ),
        NaicsEntry(
            code="72",
            title="Accommodation and Food Services",
        ),
        NaicsEntry(
            code="81",
            title="Other Services (except Public Administration)",
        ),
        NaicsEntry(code="92", title="Public Administration"),
    ]
)
