"""
Ontology adapter – single import point for canonical models and templates.

Tries to import from the real ``ontology_core`` library first (internal CHG
Operating System package).  If it is not installed, falls back transparently
to the stub implementations in :mod:`data_platform._stubs.ontology_stubs`.

Usage::

    from data_platform.ontology_adapter import Company, Person, Project, TemplateLibrary

    person = Person(name="Alice", email="alice@example.com")
"""

from __future__ import annotations

try:
    from ontology_core.models import Company, Person, Project  # type: ignore[import-not-found]
    from ontology_core.templates import TemplateLibrary  # type: ignore[import-not-found]

    ONTOLOGY_CORE_AVAILABLE = True
except ImportError:
    from data_platform._stubs.ontology_stubs import (  # type: ignore[assignment]
        Company,
        Person,
        Project,
        TemplateLibrary,
    )

    ONTOLOGY_CORE_AVAILABLE = False

__all__ = [
    "Company",
    "ONTOLOGY_CORE_AVAILABLE",
    "Person",
    "Project",
    "TemplateLibrary",
]
