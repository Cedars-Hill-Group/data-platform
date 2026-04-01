"""
Ontology adapter – single import point for canonical models and templates.

The current ``ontology-core`` package exposes modules under the ``ontology``
namespace and includes entity and property-catalog tooling.

This project keeps its existing in-memory canonical model contract for ETL and
repository operations, while optionally importing property catalog classes from
``ontology-core`` when available.

If dependencies are unavailable, this module falls back to local stubs.

Usage::

    from data_platform.ontology_adapter import Company, Person, Property, TemplateLibrary

    person = Person(name="Alice", email="alice@example.com")

    # ``Project`` is a backward-compatible alias for ``Property``.
    from data_platform.ontology_adapter import Project  # noqa: F401

Catalog types::

    from data_platform.ontology_adapter import (
        AttributesCatalog,
        NaicsCatalog,
        DEFAULT_ATTRIBUTES_CATALOG,
        DEFAULT_NAICS_CATALOG,
    )
"""

from __future__ import annotations

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
    Company,
    Person,
    Project,
    Property,
    TemplateLibrary,
)

try:
    from ontology.properties.collector import PropertyCollector  # type: ignore[import-not-found]
    from ontology.properties.models import (  # type: ignore[import-not-found]
        PropertyCatalog,
        PropertyValue,
    )

    ONTOLOGY_CORE_AVAILABLE = True
except ImportError:
    PropertyCatalog = None  # type: ignore[assignment]
    PropertyCollector = None  # type: ignore[assignment]
    PropertyValue = None  # type: ignore[assignment]
    ONTOLOGY_CORE_AVAILABLE = False

# Attempt to override entity and catalog implementations with ontology-core
# versions when available.
try:
    from ontology.entities.property import Property  # type: ignore[import-not-found,no-redef]

    #: Keep ``Project`` in sync with the overridden ``Property`` from ontology-core.
    Project = Property  # type: ignore[misc]
except ImportError:
    pass  # Already imported from stubs above.

try:
    from ontology.catalogs.attributes import (
        AttributesCatalog,  # type: ignore[import-not-found,no-redef]
    )
    from ontology.catalogs.naics import NaicsCatalog  # type: ignore[import-not-found,no-redef]
except ImportError:
    pass  # Already imported from stubs above.

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
]
