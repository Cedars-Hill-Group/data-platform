"""Sanitize Company Markdown Metadata Tool.

Walks every company markdown file in the Knowledge Base and performs three
LLM-assisted enrichment tasks:

1. **Normalize Metadata to Properties Catalog** – For each property defined in
   the attributes catalog, use an LLM classification call to select the
   canonical value(s) that best describe the company, then write the result
   back to the front-matter.

2. **Company Website Identification** – If the ``website`` field is absent or
   empty, query an LLM (using the website-agent prompt) to identify the
   official URL and populate the field.

3. **NAICS Sector Classification** – Use an LLM call to assign the most
   appropriate NAICS code from the NAICS sector catalog and store the result
   in ``naics_code`` / ``naics_title`` / ``naics_sector_code`` /
   ``naics_sector_title`` metadata fields.

Example::

    from data_platform.actions.llm_client import LLMClient
    from data_platform.actions.sanitize_company import CompanySanitizer

    client = LLMClient(api_key="sk-...")
    sanitizer = CompanySanitizer(
        kb_root=None,  # Uses knowledge_base.path from config.yaml
        llm_client=client,
    )
    results = sanitizer.sanitize_all(limit=5)
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import frontmatter

from data_platform.config import get_config
from data_platform.knowledge_base.reader import KnowledgeBaseReader, ParsedDocument
from data_platform.log import get_logger
from data_platform.ontology_adapter import (
    AttributesCatalog,
    CatalogProperty,
    CatalogPropertyValue,
    NaicsCatalog,
    NaicsEntry,
    get_attributes_catalog,
    get_naics_catalog,
)

if TYPE_CHECKING:
    from data_platform.actions.llm_client import LLMClient

logger = get_logger(__name__)


class _DatetimeEncoder(json.JSONEncoder):
    """JSON encoder that serializes ``datetime`` and ``date`` values."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, date):
            return obj.isoformat()
        return super().default(obj)


_NORMALIZE_SYSTEM = (
    "You are a classification analyst. Your job is to read descriptive information "
    "about a company and identify which of the provided values apply to the "
    "company for a particular metadata property. Base your selections solely on the "
    "human-readable descriptions provided for each value, and coerce existing values to "
    "the closest matching option(s) from the provided list. Do not reduce the number of "
    "existing metadata values. You must identify at least the same number of values as currently exist "
    "in the metadata for that property, even if that means selecting multiple values with similar descriptions. "
)

_NORMALIZE_USER = """\
Property field: {field}
Property description: {field_description}
Accept multiple values: {accept_multiple}

Available values and their descriptions:
{values_list}

Company metadata:
{metadata}

Company description (body text):
{body_text}

Based on the company information above, which of the available values apply to \
the "{field}" property?
{multiple_instruction}

Return ONLY a JSON array of matching value strings.
Examples of valid responses:
  ["private_equity"]
  ["technology", "healthcare"]
  []
Do NOT include any explanation or surrounding text — only the JSON array.
"""

_WEBSITE_AGENT_SYSTEM = (
    "You are a research assistant. Your sole task is to identify the official website "
    "URL for a company based on the information provided."
)

_WEBSITE_AGENT_USER = """\
Identify the official website for the following company.

Company metadata:
{metadata}

Company description (body text):
{body_text}

{focus_context}

Return ONLY the full URL (e.g. https://www.example.com).
If you cannot determine the website, return the single word: null
"""

_NAICS_SYSTEM = (
    "You are a business classification analyst specializing in the North American "
    "Industry Classification System (NAICS). Classify companies to the most specific "
    "NAICS level possible given the available information."
)

_NAICS_USER = """\
Classify the following company using the NAICS hierarchy.

Company metadata:
{metadata}

Company description (body text):
{body_text}

NAICS top-level sectors:
{naics_sectors}

Return ONLY a JSON object with these exact keys:
  naics_sector_code  – 2-digit sector code (e.g. "51")
  naics_sector_title – sector title (e.g. "Information")
  naics_code         – most specific NAICS code that applies (e.g. "5112")
  naics_title        – title for that specific code (e.g. "Software Publishers")

Do NOT include any explanation or surrounding text — only the JSON object.
"""


class SanitizeResult:
    """Result of sanitizing a single company markdown file."""

    __slots__ = ("file_path", "changes", "error", "success")

    def __init__(
        self,
        file_path: Path,
        changes: dict[str, Any],
        error: str | None = None,
    ) -> None:
        self.file_path = file_path
        self.changes = changes
        self.error = error
        self.success = error is None

    def __repr__(self) -> str:
        return (
            f"SanitizeResult(file={self.file_path.name!r}, "
            f"changes={sorted(self.changes)!r}, "
            f"error={self.error!r})"
        )


class CompanySanitizer:
    """Walk company markdown files and sanitize their metadata using LLM calls.

    Catalogs are loaded from the documented ``ontology.registry`` API via the
    adapter when not explicitly provided. Positional catalog arguments are still
    accepted for backward compatibility and for unit tests.
    """

    def __init__(
        self,
        kb_root: Path | str | None,
        llm_client: LLMClient,
        attributes_catalog: AttributesCatalog | dict[str, Any] | None = None,
        naics_catalog: NaicsCatalog | dict[str, Any] | None = None,
        *,
        companies_folder: str = "companies",
        dry_run: bool = False,
        body_text_limit: int = 2000,
    ) -> None:
        resolved_kb_root = (
            Path(kb_root)
            if kb_root is not None
            else Path(get_config().knowledge_base.path)
        )

        self._kb_root = resolved_kb_root
        self._llm = llm_client
        self._attributes = self._coerce_attributes_catalog(attributes_catalog)
        self._naics = self._coerce_naics_catalog(naics_catalog)
        self._dry_run = dry_run
        self._body_text_limit = body_text_limit
        self._reader = KnowledgeBaseReader(
            resolved_kb_root,
            folder_map={"company": companies_folder},
        )

    @staticmethod
    def _coerce_attributes_catalog(
        catalog: AttributesCatalog | dict[str, Any] | None,
    ) -> AttributesCatalog:
        if catalog is None:
            return get_attributes_catalog()
        if isinstance(catalog, AttributesCatalog):
            return catalog
        if not isinstance(catalog, dict):
            logger.warning(
                "Unsupported attributes catalog type %r; falling back to default catalog",
                type(catalog).__name__,
            )
            return get_attributes_catalog()

        if "properties" in catalog:
            try:
                return AttributesCatalog.model_validate(catalog)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Invalid 'properties' attributes catalog payload; attempting raw-map fallback"
                )

        properties: list[CatalogProperty] = []
        for field, raw_definition in catalog.items():
            if not isinstance(field, str) or field.startswith("$"):
                continue

            description = field.replace("_", " ").title()
            accept_multiple_values = field == "focus"

            if isinstance(raw_definition, list):
                raw_values: Any = raw_definition
            elif isinstance(raw_definition, dict):
                raw_values = raw_definition.get("values", [])
                description = str(raw_definition.get("description") or description)
                accept_multiple_values = bool(
                    raw_definition.get("accept_multiple_values", accept_multiple_values)
                )
            else:
                continue

            if not isinstance(raw_values, list):
                continue

            values: list[CatalogPropertyValue] = []
            for raw_value in raw_values:
                if isinstance(raw_value, dict):
                    try:
                        values.append(CatalogPropertyValue.model_validate(raw_value))
                    except Exception:  # noqa: BLE001
                        continue
                elif isinstance(raw_value, str):
                    values.append(
                        CatalogPropertyValue(
                            value=raw_value,
                            description=raw_value,
                        )
                    )

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

        if not properties:
            logger.warning(
                "No valid properties found in provided attributes catalog; using default catalog"
            )
            return get_attributes_catalog()

        return AttributesCatalog(properties=properties)

    @staticmethod
    def _coerce_naics_catalog(catalog: NaicsCatalog | dict[str, Any] | None) -> NaicsCatalog:
        if catalog is None:
            return get_naics_catalog()
        if isinstance(catalog, NaicsCatalog):
            return catalog
        if not isinstance(catalog, dict):
            logger.warning(
                "Unsupported NAICS catalog type %r; falling back to default catalog",
                type(catalog).__name__,
            )
            return get_naics_catalog()

        if "sectors" in catalog:
            try:
                return NaicsCatalog.model_validate(catalog)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Invalid 'sectors' NAICS catalog payload; attempting raw-map fallback"
                )

        raw_sectors = catalog.get("naics_sectors", [])
        sectors: list[NaicsEntry] = []
        if isinstance(raw_sectors, list):
            for entry in raw_sectors:
                if not isinstance(entry, dict):
                    continue
                try:
                    sectors.append(NaicsEntry.model_validate(entry))
                except Exception:  # noqa: BLE001
                    continue

        if not sectors:
            logger.warning(
                "No valid sectors found in provided NAICS catalog; using default catalog"
            )
            return get_naics_catalog()

        return NaicsCatalog(sectors=sectors)

    @staticmethod
    def _format_changes(doc: ParsedDocument, changes: dict[str, Any]) -> str:
        formatted = []
        for field, new_value in changes.items():
            old_value = doc.metadata.get(field, "<not set>")
            formatted.append(f"{field}: {old_value!r} -> {new_value!r}")
        return "; ".join(formatted)

    def sanitize_all(self, limit: int | None = None) -> list[SanitizeResult]:
        files = self._reader.list_files(object_type="company")
        if limit is not None:
            files = files[:limit]
        logger.info(
            "Starting company metadata sanitization: %d file(s)%s%s",
            len(files),
            f" (limit={limit})" if limit is not None else "",
            " [dry run]" if self._dry_run else "",
        )
        results: list[SanitizeResult] = []
        for file_path in files:
            results.append(self.sanitize_file(file_path))
        logger.info(
            "Sanitization complete: %d succeeded, %d failed",
            sum(1 for result in results if result.success),
            sum(1 for result in results if not result.success),
        )
        return results

    def sanitize_file(self, file_path: Path | str) -> SanitizeResult:
        file_path = Path(file_path)
        logger.info("Sanitizing %s", file_path.name)

        try:
            doc = self._reader.read_file(file_path)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to read %s: %s", file_path.name, exc)
            return SanitizeResult(file_path, {}, error=str(exc))

        changes: dict[str, Any] = {}

        try:
            changes.update(self._normalize_properties(doc))
        except Exception as exc:  # noqa: BLE001
            logger.error("Property normalization failed for %s: %s", file_path.name, exc)

        try:
            changes.update(self._ensure_website(doc))
        except Exception as exc:  # noqa: BLE001
            logger.error("Website identification failed for %s: %s", file_path.name, exc)

        try:
            changes.update(self._classify_naics(doc))
        except Exception as exc:  # noqa: BLE001
            logger.error("NAICS classification failed for %s: %s", file_path.name, exc)

        if changes:
            formatted_changes = self._format_changes(doc, changes)
            if self._dry_run:
                logger.info("Dry run - would update %s: %s", file_path.name, formatted_changes)
            else:
                self._write_metadata(file_path, {**doc.metadata, **changes})
                logger.info("Updated %s: %s", file_path.name, formatted_changes)
        else:
            logger.info("No changes for %s", file_path.name)

        return SanitizeResult(file_path, changes)

    def _normalize_properties(self, doc: ParsedDocument) -> dict[str, Any]:
        changes: dict[str, Any] = {}

        for prop in self._attributes.properties:
            values_list = "\n".join(
                f"  - {value.value}: {value.description}" for value in prop.values
            )
            accept_multiple = prop.accept_multiple_values
            multiple_instruction = (
                "You may select multiple values if more than one applies."
                if accept_multiple
                else "Select only the single value that best applies."
            )

            user_prompt = _NORMALIZE_USER.format(
                field=prop.field,
                field_description=prop.description,
                accept_multiple=accept_multiple,
                values_list=values_list,
                metadata=json.dumps(doc.metadata, indent=2, cls=_DatetimeEncoder),
                body_text=doc.content[: self._body_text_limit],
                multiple_instruction=multiple_instruction,
            )

            try:
                raw = self._llm.chat(system=_NORMALIZE_SYSTEM, user=user_prompt)
                new_values = json.loads(raw.strip())
                if not isinstance(new_values, list):
                    logger.warning(
                        "Unexpected LLM response for field '%s' in %s - expected list, got %r",
                        prop.field,
                        doc.path.name,
                        type(new_values).__name__,
                    )
                    continue
                if not new_values:
                    continue
                changes[prop.field] = new_values if accept_multiple else new_values[0]
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning(
                    "Could not parse LLM response for field '%s' in %s: %s",
                    prop.field,
                    doc.path.name,
                    exc,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "LLM call failed for field '%s' in %s: %s",
                    prop.field,
                    doc.path.name,
                    exc,
                )

        return changes

    def _ensure_website(self, doc: ParsedDocument) -> dict[str, Any]:
        existing = doc.metadata.get("website")
        if existing and str(existing).strip():
            return {}

        focus = doc.metadata.get("focus", [])
        if isinstance(focus, list):
            focus_str = ", ".join(str(item) for item in focus)
        else:
            focus_str = str(focus)
        focus_context = (
            f"The company's primary focus areas are: {focus_str}."
            if focus_str
            else ""
        )

        try:
            from domain_services.agent_orchestration.prompts.janitor import (  # type: ignore[import-not-found]
                website_agent as website_agent_prompt,
            )

            system_prompt: str = getattr(website_agent_prompt, "SYSTEM", _WEBSITE_AGENT_SYSTEM)
            user_template: str = getattr(website_agent_prompt, "USER", _WEBSITE_AGENT_USER)
        except ImportError:
            system_prompt = _WEBSITE_AGENT_SYSTEM
            user_template = _WEBSITE_AGENT_USER

        user_prompt = user_template.format(
            metadata=json.dumps(doc.metadata, indent=2, cls=_DatetimeEncoder),
            body_text=doc.content[: self._body_text_limit],
            focus_context=focus_context,
        )

        try:
            raw = self._llm.chat(system=system_prompt, user=user_prompt)
            url = raw.strip().strip('"\'')
            if url and url.lower() != "null" and url.startswith("http"):
                return {"website": url}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Website LLM call failed for %s: %s", doc.path.name, exc)

        return {}

    def _classify_naics(self, doc: ParsedDocument) -> dict[str, Any]:
        sectors_summary = "\n".join(
            f"  {sector.code}: {sector.title}" for sector in self._naics.sectors
        )

        user_prompt = _NAICS_USER.format(
            metadata=json.dumps(doc.metadata, indent=2, cls=_DatetimeEncoder),
            body_text=doc.content[: self._body_text_limit],
            naics_sectors=sectors_summary,
        )

        try:
            raw = self._llm.chat(system=_NAICS_SYSTEM, user=user_prompt)
            naics_data = json.loads(raw.strip())
            if not isinstance(naics_data, dict):
                logger.warning(
                    "Unexpected NAICS LLM response for %s: expected dict, got %r",
                    doc.path.name,
                    type(naics_data).__name__,
                )
                return {}

            result: dict[str, Any] = {}
            for key in (
                "naics_code",
                "naics_title",
                "naics_sector_code",
                "naics_sector_title",
            ):
                if key in naics_data:
                    result[key] = naics_data[key]
            return result
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Could not parse NAICS LLM response for %s: %s", doc.path.name, exc)
        except Exception as exc:  # noqa: BLE001
            logger.warning("NAICS LLM call failed for %s: %s", doc.path.name, exc)

        return {}

    @staticmethod
    def _write_metadata(file_path: Path, metadata: dict[str, Any]) -> None:
        post = frontmatter.load(str(file_path))
        for key, value in metadata.items():
            post.metadata[key] = value
        file_path.write_text(frontmatter.dumps(post), encoding="utf-8")
