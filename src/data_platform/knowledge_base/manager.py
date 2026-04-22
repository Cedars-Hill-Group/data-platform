"""Knowledge Base manager – unified CRUD interface.

Provides a single entry point for downstream applications that need full
read/write/update/delete access to the Knowledge Base.  Every operation is
logged so that callers gain an automatic audit trail without any additional
instrumentation.

Example::

    from data_platform.knowledge_base.manager import KnowledgeBaseManager

    manager = KnowledgeBaseManager(cfg.knowledge_base.path)

    # --- Read ---
    doc  = manager.read_file(Path("kb/people/alice-smith.md"))
    docs = manager.read_all(object_type="person")

    # --- Create ---
    path = manager.create("person", name="Bob Jones", email="bob@example.com")

    # --- Update front-matter fields ---
    manager.update(path, role="Senior Engineer")

    # --- Targeted section edits ---
    manager.write_header_section(path, "Skills", "Python, SQL")
    manager.append_header_section(path, "Notes", "Joined Q4 2024.")

    # --- Delete ---
    manager.delete(path)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from data_platform.knowledge_base.reader import KnowledgeBaseReader, ParsedDocument
from data_platform.knowledge_base.writer import KnowledgeBaseWriter
from data_platform.log import get_logger
from data_platform.ontology_adapter import TemplateLibrary

logger = get_logger(__name__)


class KnowledgeBaseManager:
    """Unified CRUD interface for the Knowledge Base markdown files.

    Combines :class:`KnowledgeBaseReader` and :class:`KnowledgeBaseWriter`
    into a single object and adds a :meth:`delete` operation.  All mutating
    operations are logged at ``INFO`` level so callers have an automatic audit
    trail.

    Parameters
    ----------
    root:
        Path to the KB root directory.
    template_library:
        Template library used to render new files.  Defaults to a fresh
        :class:`~data_platform.ontology_adapter.TemplateLibrary` instance.
    folder_map:
        Optional mapping from canonical type name to sub-folder name,
        e.g. ``{"person": "people", "company": "companies", "project": "Properties"}``.
        When ``None``, the defaults from the reader/writer are used.
        Pass ``config.knowledge_base.folder_map`` to apply configured paths.
    """

    def __init__(
        self,
        root: Path | str,
        template_library: TemplateLibrary | None = None,
        folder_map: dict[str, str] | None = None,
    ) -> None:
        self._root = Path(root)
        self._reader = KnowledgeBaseReader(self._root, folder_map=folder_map)
        self._writer = KnowledgeBaseWriter(
            self._root,
            template_library=template_library,
            folder_map=folder_map,
        )
        logger.debug("KnowledgeBaseManager initialised at %s", self._root)

    @property
    def root(self) -> Path:
        """Root directory of this Knowledge Base."""
        return self._root

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def read_file(self, file_path: Path | str) -> ParsedDocument:
        """Parse a single markdown file into a :class:`ParsedDocument`.

        Parameters
        ----------
        file_path:
            Absolute (or relative-to-cwd) path to the ``.md`` file.

        Raises
        ------
        FileNotFoundError
            If *file_path* does not exist.
        ValueError
            If the file is not inside a recognised object-type sub-directory.
        """
        return self._reader.read_file(Path(file_path))

    def read_all(self, object_type: str | None = None) -> list[ParsedDocument]:
        """Read all markdown files from the KB.

        Parameters
        ----------
        object_type:
            When supplied, only files from the matching sub-directory are
            returned.  Accepted values: ``"person"``, ``"company"``,
            ``"property"`` (or ``"project"`` for backward compatibility).
            When ``None``, all types are returned.
        """
        return self._reader.read_all(object_type=object_type)

    def list_files(self, object_type: str | None = None) -> list[Path]:
        """Return paths of all ``.md`` files without parsing them.

        Parameters
        ----------
        object_type:
            When supplied, restrict to the sub-directory for that type.
        """
        return self._reader.list_files(object_type=object_type)

    def select_header_content(
        self,
        file_path: Path | str,
        headers: list[str],
        *,
        case_sensitive: bool = True,
        normalize: bool = False,
    ) -> dict[str, list[str]]:
        """Read *file_path* and return section bodies for selected headers."""
        return self._reader.select_header_content(
            Path(file_path),
            headers,
            case_sensitive=case_sensitive,
            normalize=normalize,
        )

    # ------------------------------------------------------------------
    # Write / create operations
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
            One of ``"person"``, ``"company"``, ``"property"``
            (``"project"`` is also accepted for backward compatibility).
        filename:
            Optional explicit filename (without ``.md`` extension).
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
        return self._writer.create(object_type, filename=filename, overwrite=overwrite, **fields)

    # ------------------------------------------------------------------
    # Update operations
    # ------------------------------------------------------------------

    def update(self, file_path: Path | str, **fields: Any) -> Path:
        """Merge *fields* into *file_path*'s front-matter and re-render.

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
        return self._writer.update(Path(file_path), **fields)

    def write_header_section(
        self,
        file_path: Path | str,
        header: str,
        content: str,
        *,
        create_if_missing: bool = True,
        header_level: int = 2,
        case_sensitive: bool = True,
        normalize: bool = False,
    ) -> Path:
        """Replace the body of a single markdown *header* section.

        When the header is absent and *create_if_missing* is ``True`` the
        header and content are appended to the file.
        """
        return self._writer.write_header_section(
            Path(file_path),
            header,
            content,
            create_if_missing=create_if_missing,
            header_level=header_level,
            case_sensitive=case_sensitive,
            normalize=normalize,
        )

    def write_header_sections(
        self,
        file_path: Path | str,
        sections: dict[str, str],
        *,
        create_if_missing: bool = True,
        header_level: int = 2,
        case_sensitive: bool = True,
        normalize: bool = False,
    ) -> Path:
        """Replace the bodies of one or more markdown header sections."""
        return self._writer.write_header_sections(
            Path(file_path),
            sections,
            create_if_missing=create_if_missing,
            header_level=header_level,
            case_sensitive=case_sensitive,
            normalize=normalize,
        )

    def append_header_section(
        self,
        file_path: Path | str,
        header: str,
        content: str,
        *,
        create_if_missing: bool = True,
        header_level: int = 2,
        case_sensitive: bool = True,
        normalize: bool = False,
    ) -> Path:
        """Append *content* under a specific markdown *header*.

        Existing section content is preserved; new content is added after a
        blank line.
        """
        return self._writer.append_header_section(
            Path(file_path),
            header,
            content,
            create_if_missing=create_if_missing,
            header_level=header_level,
            case_sensitive=case_sensitive,
            normalize=normalize,
        )

    def append_header_sections(
        self,
        file_path: Path | str,
        sections: dict[str, str],
        *,
        create_if_missing: bool = True,
        header_level: int = 2,
        case_sensitive: bool = True,
        normalize: bool = False,
    ) -> Path:
        """Append content to one or more markdown header sections."""
        return self._writer.append_header_sections(
            Path(file_path),
            sections,
            create_if_missing=create_if_missing,
            header_level=header_level,
            case_sensitive=case_sensitive,
            normalize=normalize,
        )

    # ------------------------------------------------------------------
    # Delete operation
    # ------------------------------------------------------------------

    def delete(self, file_path: Path | str) -> None:
        """Delete a markdown file from the Knowledge Base.

        Parameters
        ----------
        file_path:
            Path to the markdown file to remove.

        Raises
        ------
        FileNotFoundError
            If *file_path* does not exist.
        """
        self._writer.delete(Path(file_path))
