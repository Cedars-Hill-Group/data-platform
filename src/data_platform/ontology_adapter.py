"""
Ontology adapter – single import point for canonical models and templates.

The current ``ontology-core`` package exposes modules under the ``ontology``
namespace and includes entity and property-catalog tooling.

This project keeps its existing in-memory canonical model contract for ETL and
repository operations, while optionally importing property catalog classes from
``ontology-core`` when available.

If dependencies are unavailable, this module falls back to local stubs.

Usage::

    from data_platform.ontology_adapter import Company, Person, Project, TemplateLibrary

    person = Person(name="Alice", email="alice@example.com")
"""

from __future__ import annotations

from data_platform._stubs.ontology_stubs import Company, Person, Project, TemplateLibrary

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

__all__ = [
    "Company",
    "ONTOLOGY_CORE_AVAILABLE",
    "PropertyCatalog",
    "PropertyCollector",
    "PropertyValue",
    "Person",
    "Project",
    "TemplateLibrary",
]
