"""Ontology adapter for optional ontology-core integration.

This module provides a stable import surface for the rest of the project.
When ``ontology-core`` is available, entity classes are imported from it and
catalog data is loaded through the documented ``ontology.registry`` API.
When it is unavailable, local stub implementations are used instead.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from data_platform._stubs.catalogs import (
    DEFAULT_ATTRIBUTES_CATALOG,
    DEFAULT_NAICS_CATALOG,
    AttributesCatalog,
    CatalogProperty,
    CatalogPropertyValue,
    NaicsCatalog,
    NaicsEntry,
)
from data_platform._stubs.ontology_stubs import (
    Company as _StubCompany,
    Person as _StubPerson,
    Project as _StubProject,
    Property as _StubProperty,
    TemplateLibrary,
)

Company = _StubCompany
Person = _StubPerson
Project = _StubProject
Property = _StubProperty

try:
    from ontology.registry import (  # type: ignore[import-not-found]
        get_catalog as ontology_get_catalog,
        get_catalog_version,
        list_catalogs,
    )

    ONTOLOGY_CORE_AVAILABLE = True
except ImportError:
    ontology_get_catalog = None  # type: ignore[assignment]
    get_catalog_version = None  # type: ignore[assignment]
    list_catalogs = None  # type: ignore[assignment]
    ONTOLOGY_CORE_AVAILABLE = False

try:
    from ontology.entities.company import Company  # type: ignore[import-not-found,no-redef]
    from ontology.entities.person import Person  # type: ignore[import-not-found,no-redef]
    from ontology.entities.property import Property  # type: ignore[import-not-found,no-redef]

    Project = Property  # type: ignore[misc]
except ImportError:
    pass

try:
    from ontology.properties.collector import PropertyCollector  # type: ignore[import-not-found]
    from ontology.properties.models import (  # type: ignore[import-not-found]
        PropertyCatalog,
        PropertyValue,
    )
except ImportError:
    PropertyCatalog = None  # type: ignore[assignment]
    PropertyCollector = None  # type: ignore[assignment]
    PropertyValue = None  # type: ignore[assignment]

_PROPERTY_DESCRIPTIONS = {
    "firm_type": "The type of investment firm or fund structure.",
    "focus": "Primary investment focus areas, sectors, or themes.",
}

_MULTI_VALUE_FIELDS = {"firm_type", "focus"}


def _build_attributes_catalog(raw_catalog: dict[str, Any]) -> AttributesCatalog:
    # Some registries return an explicit list of property objects.
    # Example:
    #   {"properties": [{"field": "firm_type", "accept_multiple_values": true,
    #                    "values": [...]}, ...]}
    raw_properties = raw_catalog.get("properties")
    if isinstance(raw_properties, list):
        properties: list[CatalogProperty] = []
        for raw_property in raw_properties:
            if not isinstance(raw_property, dict):
                continue
            try:
                properties.append(CatalogProperty.model_validate(raw_property))
            except ValueError:
                continue
        if properties:
            return AttributesCatalog(properties=properties)

    properties: list[CatalogProperty] = []
    for field, raw_definition in raw_catalog.items():
        if field.startswith("$"):
            continue
        if field == "properties":
            continue

        description = _PROPERTY_DESCRIPTIONS.get(field, field.replace("_", " ").title())
        accept_multiple_values = field in _MULTI_VALUE_FIELDS
        raw_values: Any

        # Support both legacy format:
        #   "field": [{"value": "...", "description": "..."}, ...]
        # and rich format:
        #   "field": {
        #       "description": "...",
        #       "accept_multiple_values": true,
        #       "values": [{...}, ...]
        #   }
        if isinstance(raw_definition, list):
            raw_values = raw_definition
        elif isinstance(raw_definition, dict):
            raw_values = raw_definition.get("values", [])
            description = raw_definition.get("description") or description
            accept_multiple_values = bool(
                raw_definition.get("accept_multiple_values", accept_multiple_values)
            )
        else:
            continue

        if not isinstance(raw_values, list):
            continue

        values: list[CatalogPropertyValue] = []
        for value in raw_values:
            try:
                values.append(CatalogPropertyValue.model_validate(value))
            except ValueError:
                continue
        if not values:
            continue

        properties.append(
            CatalogProperty(
                field=field,
                description=description,
                accept_multiple_values=accept_multiple_values,
                values=values,
            )
        )
    return AttributesCatalog(properties=properties)


def _build_naics_catalog(raw_catalog: dict[str, Any]) -> NaicsCatalog:
    sectors = [
        NaicsEntry.model_validate(entry)
        for entry in raw_catalog.get("naics_sectors", [])
        if isinstance(entry, dict)
    ]
    return NaicsCatalog(sectors=sectors)


def get_catalog(name: str, version: str | None = None) -> dict[str, Any]:
    """Return a raw ontology catalog dictionary."""
    if ontology_get_catalog is None:
        raise RuntimeError("ontology-core is not available")
    return ontology_get_catalog(name, version)


@lru_cache(maxsize=1)
def get_attributes_catalog() -> AttributesCatalog:
    """Return the canonical attributes catalog as local model objects."""
    if ontology_get_catalog is None:
        return DEFAULT_ATTRIBUTES_CATALOG
    try:
        return _build_attributes_catalog(ontology_get_catalog("attributes"))
    except (FileNotFoundError, KeyError, TypeError, ValueError):
        return DEFAULT_ATTRIBUTES_CATALOG


@lru_cache(maxsize=1)
def get_naics_catalog() -> NaicsCatalog:
    """Return the canonical NAICS catalog as local model objects."""
    if ontology_get_catalog is None:
        return DEFAULT_NAICS_CATALOG
    try:
        return _build_naics_catalog(ontology_get_catalog("naics"))
    except (FileNotFoundError, KeyError, TypeError, ValueError):
        return DEFAULT_NAICS_CATALOG


def get_catalogs() -> tuple[AttributesCatalog, NaicsCatalog]:
    """Return both supported catalogs as local model objects."""
    return get_attributes_catalog(), get_naics_catalog()


__all__ = [
    "AttributesCatalog",
    "CatalogProperty",
    "CatalogPropertyValue",
    "Company",
    "DEFAULT_ATTRIBUTES_CATALOG",
    "DEFAULT_NAICS_CATALOG",
    "NaicsCatalog",
    "NaicsEntry",
    "ONTOLOGY_CORE_AVAILABLE",
    "PropertyCatalog",
    "PropertyCollector",
    "PropertyValue",
    "Person",
    "Project",
    "Property",
    "TemplateLibrary",
    "get_attributes_catalog",
    "get_catalog",
    "get_catalog_version",
    "get_catalogs",
    "get_naics_catalog",
    "list_catalogs",
]
