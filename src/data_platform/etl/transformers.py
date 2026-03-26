"""Data transformers – map raw :class:`ParsedDocument` objects to canonical models.

Each transformer handles one object type and is responsible for:
1. Pulling fields from the front-matter dict.
2. Filling in defaults (e.g. generating a UUID when ``id`` is absent).
3. Attaching the source file path for lineage tracking.
4. Returning a validated pydantic model instance.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from data_platform.knowledge_base.reader import ParsedDocument
from data_platform.log import get_logger
from data_platform.ontology_adapter import Company, Person, Project

logger = get_logger(__name__)


@dataclass
class RawDocument:
    """Lightweight container for raw data before transformation.

    Can wrap a :class:`ParsedDocument` or an arbitrary dict from another
    source (CSV row, API response, etc.).
    """

    data: dict[str, Any]
    source: str = ""
    object_type: str = ""

    @classmethod
    def from_parsed(cls, doc: ParsedDocument) -> "RawDocument":
        """Create a :class:`RawDocument` from a :class:`ParsedDocument`."""
        combined = dict(doc.metadata)
        combined["_body"] = doc.content
        return cls(
            data=combined,
            source=str(doc.path),
            object_type=doc.object_type,
        )


# ---------------------------------------------------------------------------
# Person transformer
# ---------------------------------------------------------------------------


class PersonTransformer:
    """Transforms a raw document into a :class:`Person` canonical object."""

    def transform(self, raw: RawDocument) -> Person:
        d = raw.data
        raw_name = d.get("name") or Path(raw.source).stem
        person = Person(
            id=d.get("id") or str(uuid.uuid4()),
            name=raw_name,
            email=d.get("email"),
            role=d.get("role"),
            organization=d.get("organization"),
            bio=d.get("bio") or d.get("_body"),
            tags=_parse_list(d.get("tags")),
            metadata={k: v for k, v in d.items() if not k.startswith("_") and k not in _PERSON_KNOWN},
            source_file=raw.source,
        )
        logger.debug("Transformed Person id=%s name=%r source=%s", person.id, person.name, raw.source)
        return person

    def transform_many(
        self, raws: list[RawDocument]
    ) -> tuple[list[Person], list[tuple[str, str]]]:
        """Transform a batch, collecting errors rather than raising."""
        results: list[Person] = []
        errors: list[tuple[str, str]] = []
        for raw in raws:
            try:
                results.append(self.transform(raw))
            except Exception as exc:
                logger.warning("PersonTransformer failed for source=%r: %s", raw.source, exc)
                errors.append((raw.source, str(exc)))
        logger.debug("PersonTransformer.transform_many: %d ok, %d error(s)", len(results), len(errors))
        return results, errors


_PERSON_KNOWN = {"id", "name", "email", "role", "organization", "bio", "tags"}


# ---------------------------------------------------------------------------
# Company transformer
# ---------------------------------------------------------------------------


class CompanyTransformer:
    """Transforms a raw document into a :class:`Company` canonical object."""

    def transform(self, raw: RawDocument) -> Company:
        d = raw.data
        raw_name = d.get("name") or Path(raw.source).stem
        company = Company(
            id=d.get("id") or str(uuid.uuid4()),
            name=raw_name,
            industry=d.get("industry"),
            size=d.get("size"),
            website=d.get("website"),
            description=d.get("description") or d.get("_body"),
            tags=_parse_list(d.get("tags")),
            metadata={k: v for k, v in d.items() if not k.startswith("_") and k not in _COMPANY_KNOWN},
            source_file=raw.source,
        )
        logger.debug("Transformed Company id=%s name=%r source=%s", company.id, company.name, raw.source)
        return company

    def transform_many(
        self, raws: list[RawDocument]
    ) -> tuple[list[Company], list[tuple[str, str]]]:
        results: list[Company] = []
        errors: list[tuple[str, str]] = []
        for raw in raws:
            try:
                results.append(self.transform(raw))
            except Exception as exc:
                logger.warning("CompanyTransformer failed for source=%r: %s", raw.source, exc)
                errors.append((raw.source, str(exc)))
        logger.debug("CompanyTransformer.transform_many: %d ok, %d error(s)", len(results), len(errors))
        return results, errors


_COMPANY_KNOWN = {"id", "name", "industry", "size", "website", "description", "tags"}


# ---------------------------------------------------------------------------
# Project transformer
# ---------------------------------------------------------------------------


class ProjectTransformer:
    """Transforms a raw document into a :class:`Project` canonical object."""

    def transform(self, raw: RawDocument) -> Project:
        d = raw.data
        raw_name = d.get("name") or Path(raw.source).stem
        project = Project(
            id=d.get("id") or str(uuid.uuid4()),
            name=raw_name,
            description=d.get("description") or d.get("_body"),
            status=d.get("status"),
            owner=d.get("owner"),
            members=_parse_list(d.get("members")),
            tags=_parse_list(d.get("tags")),
            metadata={k: v for k, v in d.items() if not k.startswith("_") and k not in _PROJECT_KNOWN},
            source_file=raw.source,
        )
        logger.debug("Transformed Project id=%s name=%r source=%s", project.id, project.name, raw.source)
        return project

    def transform_many(
        self, raws: list[RawDocument]
    ) -> tuple[list[Project], list[tuple[str, str]]]:
        results: list[Project] = []
        errors: list[tuple[str, str]] = []
        for raw in raws:
            try:
                results.append(self.transform(raw))
            except Exception as exc:
                logger.warning("ProjectTransformer failed for source=%r: %s", raw.source, exc)
                errors.append((raw.source, str(exc)))
        logger.debug("ProjectTransformer.transform_many: %d ok, %d error(s)", len(results), len(errors))
        return results, errors


_PROJECT_KNOWN = {"id", "name", "description", "status", "owner", "members", "tags"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_list(value: Any) -> list[str]:
    """Normalise a YAML value that should be a list of strings."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]
