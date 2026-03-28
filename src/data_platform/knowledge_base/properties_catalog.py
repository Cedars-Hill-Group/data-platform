"""Property catalog collection utilities.

Mirrors the ontology-core workflow that walks a Markdown knowledge base and
emits a machine-readable ``properties.json`` catalog consumed by downstream
apps and repositories.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from data_platform.log import get_logger
from data_platform.ontology_adapter import ONTOLOGY_CORE_AVAILABLE
from data_platform.ontology_adapter import PropertyCollector as OntologyPropertyCollector

logger = get_logger(__name__)


class PropertyValue(BaseModel):
    """A single normalised categorical value and its description."""

    value: str = Field(..., description="Normalised property value identifier.")
    description: str = Field(..., description="Human-readable description.")


class PropertyCatalog(BaseModel):
    """Catalog of allowed values for firm_type and focus properties."""

    firm_type: list[PropertyValue] = Field(default_factory=list)
    focus: list[PropertyValue] = Field(default_factory=list)

    def to_json(self, indent: int = 2) -> str:
        return self.model_dump_json(indent=indent)

    def save(self, path: str | Path, indent: int = 2) -> Path:
        output = Path(path).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(self.to_json(indent=indent), encoding="utf-8")
        return output


def collect_property_catalog(
    knowledge_base_path: str | Path,
    *,
    output_path: str | Path | None = None,
    entity_dirs: dict[str, type] | None = None,
) -> tuple[BaseModel, Path | None]:
    """Collect and optionally persist the property catalog.

    Parameters
    ----------
    knowledge_base_path:
        Root path to the markdown knowledge base.
    output_path:
        Optional destination for the emitted ``properties.json``.
    entity_dirs:
        Optional mapping of KB subdirectory name to ontology entity class.
        Forwarded to ontology-core when available.

    Returns
    -------
    tuple[BaseModel, Path | None]
        The collected catalog and the saved path (when *output_path* is set).
    """
    resolved_entity_dirs = entity_dirs or _resolve_entity_dirs(
        companies_dir="companies",
        people_dir="people",
        projects_dir="Properties",
    )

    if ONTOLOGY_CORE_AVAILABLE and OntologyPropertyCollector is not None:
        collector = OntologyPropertyCollector(knowledge_base_path, entity_dirs=resolved_entity_dirs)
        catalog = collector.collect()
    else:
        logger.warning(
            "ontology-core is not available; using local fallback collector for properties.json"
        )
        catalog = _collect_fallback(knowledge_base_path, entity_dirs=resolved_entity_dirs)

    saved: Path | None = None
    if output_path is not None:
        output_file = Path(output_path)
        save_fn = getattr(catalog, "save", None)
        if callable(save_fn):
            saved = save_fn(output_file)
        else:
            # Defensive fallback for catalog implementations without save().
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(catalog.model_dump_json(indent=2), encoding="utf-8")
            saved = output_file.resolve()

    return catalog, saved


def emit_properties_json(
    *,
    knowledge_base_path: str | Path,
    output_dir: str | Path,
    companies_dir: str = "companies",
    people_dir: str = "people",
    projects_dir: str = "Properties",
) -> tuple[BaseModel, Path]:
    """Mirror ontology-core's KB walk and ``properties.json`` emission flow."""
    entity_dirs = _resolve_entity_dirs(
        companies_dir=companies_dir,
        people_dir=people_dir,
        projects_dir=projects_dir,
    )
    output_path = Path(output_dir) / "properties.json"
    catalog, saved = collect_property_catalog(
        knowledge_base_path,
        output_path=output_path,
        entity_dirs=entity_dirs,
    )
    assert saved is not None
    return catalog, saved


def _collect_fallback(
    knowledge_base_path: str | Path,
    entity_dirs: dict[str, type] | None = None,
) -> PropertyCatalog:
    kb_path = Path(knowledge_base_path).resolve()
    directory_names = list(entity_dirs) if entity_dirs else ["companies", "people", "Properties"]

    firm_type_values: dict[str, PropertyValue] = {}
    focus_values: dict[str, PropertyValue] = {}

    for subdir in directory_names:
        root = kb_path / subdir
        if not root.is_dir():
            continue
        for md_file in sorted(root.glob("*.md")):
            try:
                import frontmatter

                post = frontmatter.load(str(md_file))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Skipping malformed markdown file %s: %s", md_file, exc)
                continue

            for raw in _as_list(post.metadata.get("firm_type")):
                key = _normalise(raw)
                if key and key not in firm_type_values:
                    firm_type_values[key] = PropertyValue(
                        value=key,
                        description=f"Auto-generated description for firm_type value '{key}'.",
                    )

            for raw in _as_list(post.metadata.get("focus")):
                key = _normalise(raw)
                if key and key not in focus_values:
                    focus_values[key] = PropertyValue(
                        value=key,
                        description=f"Auto-generated description for focus value '{key}'.",
                    )

    return PropertyCatalog(
        firm_type=[firm_type_values[key] for key in sorted(firm_type_values)],
        focus=[focus_values[key] for key in sorted(focus_values)],
    )


def _resolve_entity_dirs(
    *,
    companies_dir: str,
    people_dir: str,
    projects_dir: str,
) -> dict[str, type] | None:
    if not ONTOLOGY_CORE_AVAILABLE:
        return {
            companies_dir: object,
            people_dir: object,
            projects_dir: object,
        }

    try:
        from ontology.entities.company import Company
        from ontology.entities.person import Person
        from ontology.entities.project import Project
    except ImportError:
        return {
            companies_dir: object,
            people_dir: object,
            projects_dir: object,
        }

    return {
        companies_dir: Company,
        people_dir: Person,
        projects_dir: Project,
    }


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def _normalise(value: str) -> str:
    normalised = "_".join(value.strip().lower().replace("-", " ").split())
    return normalised
