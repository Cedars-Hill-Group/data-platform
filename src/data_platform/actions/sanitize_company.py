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
   appropriate NAICS code from the full NAICS hierarchy and store the result
   in ``naics_code`` / ``naics_title`` / ``naics_sector_code`` /
   ``naics_sector_title`` metadata fields.

Example::

    from data_platform.actions.llm_client import LLMClient
    from data_platform.actions.sanitize_company import CompanySanitizer
    from data_platform.ontology_adapter import DEFAULT_ATTRIBUTES_CATALOG, DEFAULT_NAICS_CATALOG

    client = LLMClient(api_key="sk-...")
    sanitizer = CompanySanitizer(
        kb_root=None,  # Uses knowledge_base.path from config.yaml
        llm_client=client,
        attributes_catalog=DEFAULT_ATTRIBUTES_CATALOG,
        naics_catalog=DEFAULT_NAICS_CATALOG,
    )
    results = sanitizer.sanitize_all()
    for r in results:
        print(r)

    # Test on a limited number of files first:
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
from data_platform.ontology_adapter import AttributesCatalog, NaicsCatalog

if TYPE_CHECKING:
    from data_platform.actions.llm_client import LLMClient

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# JSON encoder for serialization
# ---------------------------------------------------------------------------


class _DatetimeEncoder(json.JSONEncoder):
    """JSON encoder that handles datetime and date objects by converting them to ISO format strings."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, date):
            return obj.isoformat()
        return super().default(obj)

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_NORMALIZE_SYSTEM = (
    "You are a classification analyst. Your job is to read descriptive information "
    "about a company and identify which of the provided canonical values apply to the "
    "company for a particular metadata property. Base your selections solely on the "
    "human-readable descriptions provided for each value."
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

# Fallback website-agent prompt (used when domain-services is not installed).
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


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


class SanitizeResult:
    """Result of sanitizing a single company markdown file.

    Attributes
    ----------
    file_path:
        Absolute path to the processed file.
    changes:
        Mapping of field name to the new value written (or that *would* be
        written in dry-run mode).
    error:
        Error message if the file could not be processed; *None* on success.
    success:
        ``True`` when no unhandled error occurred.
    """

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


# ---------------------------------------------------------------------------
# Main sanitizer
# ---------------------------------------------------------------------------


class CompanySanitizer:
    """Walk company markdown files and sanitize their metadata using LLM calls.

    The sanitizer performs three passes over each file:

    1. **Metadata normalisation** – maps each field defined in
       *attributes_catalog* to canonical ontology values.
    2. **Website identification** – populates a missing ``website`` field.
    3. **NAICS classification** – assigns the company a NAICS code.

    Parameters
    ----------
    kb_root:
        Root directory of the markdown Knowledge Base. If ``None``, the value
        is loaded from ``config.yaml`` via
        ``get_config().knowledge_base.path``.
    llm_client:
        An :class:`~data_platform.actions.llm_client.LLMClient` instance used
        for all LLM calls.
    attributes_catalog:
        :class:`~data_platform.ontology_adapter.AttributesCatalog` describing
        the metadata properties and their allowed values.
    naics_catalog:
        :class:`~data_platform.ontology_adapter.NaicsCatalog` containing the
        full NAICS hierarchy.
    companies_folder:
        Sub-folder name for company documents (default: ``"companies"``).
    dry_run:
        When ``True``, compute what changes *would* be made but do not write
        anything to disk.
    body_text_limit:
        Maximum number of characters of the markdown body sent to the LLM.
        Longer bodies are truncated to reduce token usage.
    """

    def __init__(
        self,
        kb_root: Path | str | None,
        llm_client: LLMClient,
        attributes_catalog: AttributesCatalog,
        naics_catalog: NaicsCatalog,
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
        self._attributes = attributes_catalog
        self._naics = naics_catalog
        self._dry_run = dry_run
        self._body_text_limit = body_text_limit

        self._reader = KnowledgeBaseReader(
            resolved_kb_root,
            folder_map={"company": companies_folder},
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def _format_changes(doc: ParsedDocument, changes: dict[str, Any]) -> str:
        """Format field changes as 'field: old_value -> new_value' for logging."""
        formatted = []
        for field, new_value in changes.items():
            old_value = doc.metadata.get(field, "<not set>")
            formatted.append(f"{field}: {old_value!r} -> {new_value!r}")
        return "; ".join(formatted)

    def sanitize_all(self, limit: int | None = None) -> list[SanitizeResult]:
        """Sanitize company markdown files in the Knowledge Base.

        Parameters
        ----------
        limit:
            When provided, process at most *limit* files.  Useful for a
            quick test-run on a subset of the Knowledge Base before committing
            to the full sanitization.  When ``None`` (the default), all files
            are processed.

        Returns
        -------
        list[SanitizeResult]
            One result per company file processed.
        """
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
            result = self.sanitize_file(file_path)
            results.append(result)
        logger.info(
            "Sanitization complete: %d succeeded, %d failed",
            sum(1 for r in results if r.success),
            sum(1 for r in results if not r.success),
        )
        return results

    def sanitize_file(self, file_path: Path | str) -> SanitizeResult:
        """Sanitize a single company markdown file.

        Parameters
        ----------
        file_path:
            Path to the ``.md`` file to process.

        Returns
        -------
        SanitizeResult
            Contains the fields changed and any error that occurred.
        """
        file_path = Path(file_path)
        logger.info("Sanitizing %s", file_path.name)

        try:
            doc = self._reader.read_file(file_path)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to read %s: %s", file_path.name, exc)
            return SanitizeResult(file_path, {}, error=str(exc))

        changes: dict[str, Any] = {}

        # 1. Normalize metadata against the properties catalog.
        try:
            changes.update(self._normalize_properties(doc))
        except Exception as exc:  # noqa: BLE001
            logger.error("Property normalization failed for %s: %s", file_path.name, exc)

        # 2. Ensure the website field is populated.
        try:
            changes.update(self._ensure_website(doc))
        except Exception as exc:  # noqa: BLE001
            logger.error("Website identification failed for %s: %s", file_path.name, exc)

        # 3. Classify via NAICS.
        try:
            changes.update(self._classify_naics(doc))
        except Exception as exc:  # noqa: BLE001
            logger.error("NAICS classification failed for %s: %s", file_path.name, exc)

        if changes:
            formatted_changes = self._format_changes(doc, changes)
            if self._dry_run:
                logger.info(
                    "Dry run – would update %s: %s",
                    file_path.name,
                    formatted_changes,
                )
            else:
                self._write_metadata(file_path, {**doc.metadata, **changes})
                logger.info("Updated %s: %s", file_path.name, formatted_changes)
        else:
            logger.info("No changes for %s", file_path.name)

        return SanitizeResult(file_path, changes)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _normalize_properties(self, doc: ParsedDocument) -> dict[str, Any]:
        """Run the metadata-normalization LLM pass."""
        changes: dict[str, Any] = {}

        for prop in self._attributes.properties:
            values_list = "\n".join(
                f"  - {v.value}: {v.description}" for v in prop.values
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
                        "Unexpected LLM response for field '%s' in %s – expected list, got %r",
                        prop.field, doc.path.name, type(new_values).__name__,
                    )
                    continue

                if not new_values:
                    continue  # Empty list → no change.

                if accept_multiple:
                    changes[prop.field] = new_values
                else:
                    changes[prop.field] = new_values[0]

            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning(
                    "Could not parse LLM response for field '%s' in %s: %s",
                    prop.field, doc.path.name, exc,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "LLM call failed for field '%s' in %s: %s",
                    prop.field, doc.path.name, exc,
                )

        return changes

    def _ensure_website(self, doc: ParsedDocument) -> dict[str, Any]:
        """Populate the ``website`` field if it is absent or empty."""
        existing = doc.metadata.get("website")
        if existing and str(existing).strip():
            return {}

        # Build focus context for the prompt.
        focus = doc.metadata.get("focus", [])
        if isinstance(focus, list):
            focus_str = ", ".join(str(f) for f in focus)
        else:
            focus_str = str(focus)
        focus_context = (
            f"The company's primary focus areas are: {focus_str}."
            if focus_str
            else ""
        )

        # Try to load the website-agent prompt from domain-services; fall back
        # to the built-in stub prompt.
        try:
            from domain_services.agent_orchestration.prompts.janitor import (  # type: ignore[import-not-found]
                website_agent as _wa,
            )
            system_prompt: str = getattr(_wa, "SYSTEM", _WEBSITE_AGENT_SYSTEM)
            user_template: str = getattr(_wa, "USER", _WEBSITE_AGENT_USER)
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
            url = raw.strip().strip("\"'")
            if url and url.lower() != "null" and url.startswith("http"):
                return {"website": url}
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Website LLM call failed for %s: %s", doc.path.name, exc
            )

        return {}

    def _classify_naics(self, doc: ParsedDocument) -> dict[str, Any]:
        """Assign a NAICS code to the company."""
        sectors_summary = "\n".join(
            f"  {s.code}: {s.title}" for s in self._naics.sectors
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
                    doc.path.name, type(naics_data).__name__,
                )
                return {}

            result: dict[str, Any] = {}
            for key in ("naics_code", "naics_title", "naics_sector_code", "naics_sector_title"):
                if key in naics_data:
                    result[key] = naics_data[key]
            return result

        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning(
                "Could not parse NAICS LLM response for %s: %s",
                doc.path.name, exc,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("NAICS LLM call failed for %s: %s", doc.path.name, exc)

        return {}

    @staticmethod
    def _write_metadata(file_path: Path, metadata: dict[str, Any]) -> None:
        """Overwrite the front-matter of *file_path* with *metadata*.

        The markdown body is preserved unchanged.
        """
        post = frontmatter.load(str(file_path))
        for key, value in metadata.items():
            post.metadata[key] = value
        file_path.write_text(frontmatter.dumps(post), encoding="utf-8")
