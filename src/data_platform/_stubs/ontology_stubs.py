"""
Stub implementations of the canonical ontology models and template library.

These stubs mirror the public interface expected from the ``ontology_core``
library (internal CHG Operating System package).  They are used automatically
when ``ontology_core`` is not installed (e.g. in CI, local development, or
unit tests).

When ``ontology_core`` *is* installed, the real implementations take
precedence via :mod:`data_platform.ontology_adapter`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Canonical object models
# ---------------------------------------------------------------------------


class Person(BaseModel):
    """Canonical representation of a person in the knowledge base."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    email: str | None = None
    role: str | None = None
    organization: str | None = None
    bio: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_file: str | None = Field(
        None, description="Relative path of the originating markdown file."
    )

    model_config = {"extra": "allow"}


class Company(BaseModel):
    """Canonical representation of a company in the knowledge base."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    industry: str | None = None
    size: str | None = None
    website: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_file: str | None = Field(
        None, description="Relative path of the originating markdown file."
    )

    model_config = {"extra": "allow"}


class Property(BaseModel):
    """Canonical representation of a property in the knowledge base.

    Replaces the former ``Project`` entity; ``Project`` is retained as a
    backward-compatible alias.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str | None = None
    status: str | None = None
    owner: str | None = None
    members: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_file: str | None = Field(
        None, description="Relative path of the originating markdown file."
    )

    model_config = {"extra": "allow"}


#: Backward-compatible alias – prefer :class:`Property` in new code.
Project = Property


# ---------------------------------------------------------------------------
# Template library
# ---------------------------------------------------------------------------

_PERSON_TEMPLATE = """\
---
id: {id}
name: {name}
email: {email}
role: {role}
organization: {organization}
tags: []
---

# {name}

> Add a brief bio here.
"""

_COMPANY_TEMPLATE = """\
---
id: {id}
name: {name}
industry: {industry}
size: {size}
website: {website}
tags: []
---

# {name}

> Add a company description here.
"""

_PROPERTY_TEMPLATE = """\
---
id: {id}
name: {name}
status: {status}
owner: {owner}
members: []
tags: []
---

# {name}

> Add a property description here.
"""

#: Backward-compatible alias – prefer ``_PROPERTY_TEMPLATE`` in new code.
_PROJECT_TEMPLATE = _PROPERTY_TEMPLATE


class TemplateLibrary:
    """Provides markdown templates for each canonical object type.

    When ``ontology_core`` is installed its :class:`TemplateLibrary` is used;
    otherwise this stub implementation is sufficient for development and
    testing.
    """

    _templates: dict[str, str] = {
        "person": _PERSON_TEMPLATE,
        "company": _COMPANY_TEMPLATE,
        "property": _PROPERTY_TEMPLATE,
        # "project" kept as a backward-compatible alias.
        "project": _PROPERTY_TEMPLATE,
    }

    def get_template(self, object_type: str) -> str:
        """Return the markdown template for *object_type*.

        Parameters
        ----------
        object_type:
            One of ``"person"``, ``"company"``, or ``"property"``
            (``"project"`` is also accepted for backward compatibility;
            case-insensitive).

        Raises
        ------
        KeyError
            If no template exists for the requested type.
        """
        key = object_type.lower()
        if key not in self._templates:
            raise KeyError(
                f"No template for object type '{object_type}'. "
                f"Available: {sorted(self._templates)}"
            )
        return self._templates[key]

    def render(self, object_type: str, **fields: Any) -> str:
        """Render a template with the supplied fields.

        Unknown fields are silently ignored.  Missing fields are replaced with
        an empty string so the template always produces valid markdown.
        """
        template = self.get_template(object_type)
        # Collect all placeholder names and set defaults
        import string

        placeholders = {
            fname
            for _, fname, _, _ in string.Formatter().parse(template)
            if fname is not None
        }
        context = {k: "" for k in placeholders}
        context.update({k: v for k, v in fields.items() if k in placeholders})
        return template.format_map(context)

    @property
    def available_types(self) -> list[str]:
        """List of object types with registered templates."""
        return sorted(self._templates)
