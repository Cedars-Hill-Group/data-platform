"""Knowledge Base markdown file writer.

Creates new markdown files in the KB from ontology objects or raw field dicts,
using templates provided by the :class:`~data_platform.ontology_adapter.TemplateLibrary`.

Example::

    from data_platform.knowledge_base.writer import KnowledgeBaseWriter
    from data_platform.ontology_adapter import TemplateLibrary

    writer = KnowledgeBaseWriter(root="/kb", template_library=TemplateLibrary())
    path = writer.create("person", name="Alice", email="alice@example.com")
    # → /kb/people/alice.md
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from data_platform.log import get_logger
from data_platform.ontology_adapter import TemplateLibrary

logger = get_logger(__name__)


# Map canonical type name → sub-directory
_TYPE_TO_DIR: dict[str, str] = {
    "person": "people",
    "company": "companies",
    "project": "projects",
}


def _slugify(text: str) -> str:
    """Convert *text* to a safe filename slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-") or "untitled"


class KnowledgeBaseWriter:
    """Creates and updates markdown files in the Knowledge Base.

    Parameters
    ----------
    root:
        Path to the KB root directory.
    template_library:
        Template library instance to render new files.
    folder_map:
        Optional mapping from canonical type name to sub-folder name,
        e.g. ``{"person": "people", "company": "companies", "project": "projects"}``.
        When *None*, the defaults from :data:`_TYPE_TO_DIR` are used.
        Pass ``config.knowledge_base.folder_map`` to use configured paths.
    """

    def __init__(
        self,
        root: Path | str,
        template_library: TemplateLibrary | None = None,
        folder_map: dict[str, str] | None = None,
    ) -> None:
        self._root = Path(root)
        self._templates = template_library or TemplateLibrary()
        self._type_to_dir: dict[str, str] = dict(folder_map) if folder_map is not None else dict(_TYPE_TO_DIR)

    @property
    def root(self) -> Path:
        return self._root

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create(
        self,
        object_type: str,
        filename: str | None = None,
        overwrite: bool = False,
        **fields: Any,
    ) -> Path:
        """Create a new markdown file from the template for *object_type*.

        Parameters
        ----------
        object_type:
            One of ``"person"``, ``"company"``, ``"project"``.
        filename:
            Optional explicit filename (without ``.md`` extension).  Defaults
            to a slug derived from the ``name`` field.
        overwrite:
            When ``False`` (default), raise ``FileExistsError`` if the file
            already exists.
        **fields:
            Key/value pairs forwarded to the template renderer.

        Returns
        -------
        Path
            Absolute path to the newly created file.
        """
        dir_name = self._type_dir(object_type)
        dest_dir = self._root / dir_name
        dest_dir.mkdir(parents=True, exist_ok=True)

        if filename is None:
            name = str(fields.get("name", "untitled"))
            filename = _slugify(name)

        dest_path = dest_dir / f"{filename}.md"
        if dest_path.exists() and not overwrite:
            logger.warning("File already exists and overwrite=False: %s", dest_path)
            raise FileExistsError(
                f"File already exists: {dest_path}. Pass overwrite=True to replace it."
            )

        content = self._templates.render(object_type, **fields)
        dest_path.write_text(content, encoding="utf-8")
        logger.info("Created %s file: %s", object_type, dest_path)
        return dest_path

    def update(self, file_path: Path | str, **fields: Any) -> Path:
        """Overwrite *file_path* with a freshly rendered template.

        The object type is inferred from the parent directory name.

        Parameters
        ----------
        file_path:
            Path to the existing markdown file.
        **fields:
            Updated field values.

        Returns
        -------
        Path
            The (same) file path after writing.
        """
        import frontmatter  # noqa: PLC0415

        file_path = Path(file_path)
        if not file_path.exists():
            logger.error("Cannot update – file not found: %s", file_path)
            raise FileNotFoundError(f"File not found: {file_path}")

        # Merge existing front-matter with supplied fields
        post = frontmatter.load(str(file_path))
        merged = dict(post.metadata)
        merged.update(fields)
        logger.debug("Updating %s with %d field(s)", file_path.name, len(fields))

        # Determine object type from parent dir name
        parent_name = file_path.parent.name
        reverse_map = {v: k for k, v in self._type_to_dir.items()}
        object_type = reverse_map.get(parent_name)
        if object_type is None:
            raise ValueError(
                f"Cannot determine object type from directory '{parent_name}'. "
                f"Expected one of: {sorted(_TYPE_TO_DIR)}"
            )

        content = self._templates.render(object_type, **merged)
        file_path.write_text(content, encoding="utf-8")
        logger.info("Updated %s file: %s", object_type, file_path)
        return file_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _type_dir(self, object_type: str) -> str:
        key = object_type.lower()
        if key not in self._type_to_dir:
            raise ValueError(
                f"Unknown object type: '{object_type}'. "
                f"Expected one of: {sorted(self._type_to_dir)}"
            )
        return self._type_to_dir[key]
