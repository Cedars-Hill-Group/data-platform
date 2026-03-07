"""Knowledge Base markdown file reader.

The Knowledge Base is a directory of markdown files organised by object type::

    <kb_root>/
        people/
            alice-smith.md
            bob-jones.md
        companies/
            acme-corp.md
        projects/
            project-alpha.md

Each file contains a YAML front-matter block followed by free-form markdown
content.  The reader parses both sections and returns them as structured dicts.

Example front-matter::

    ---
    id: abc-123
    name: Alice Smith
    email: alice@example.com
    role: Engineer
    organization: Acme Corp
    tags: [python, data]
    ---

    # Alice Smith

    Alice is a senior engineer at Acme Corp.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import frontmatter

from data_platform.log import get_logger

logger = get_logger(__name__)


# Recognised sub-directory names mapped to canonical object type names.
OBJECT_TYPE_DIRS: dict[str, str] = {
    "people": "person",
    "companies": "company",
    "projects": "project",
}


class ParsedDocument:
    """Result of parsing a single markdown file.

    Attributes
    ----------
    path:
        Absolute path to the source file.
    object_type:
        Canonical object type (``"person"``, ``"company"``, ``"project"``).
    metadata:
        Parsed YAML front-matter as a dict.
    content:
        The markdown body text (everything after the front-matter block).
    """

    __slots__ = ("path", "object_type", "metadata", "content")

    def __init__(
        self,
        path: Path,
        object_type: str,
        metadata: dict[str, Any],
        content: str,
    ) -> None:
        self.path = path
        self.object_type = object_type
        self.metadata = metadata
        self.content = content

    def __repr__(self) -> str:
        return (
            f"ParsedDocument(path={self.path.name!r}, "
            f"object_type={self.object_type!r}, "
            f"metadata_keys={sorted(self.metadata)!r})"
        )


class KnowledgeBaseReader:
    """Reads markdown files from the Knowledge Base root directory.

    Parameters
    ----------
    root:
        Path to the KB root directory (from ``config.yaml``).
    folder_map:
        Optional mapping from canonical type name to sub-folder name,
        e.g. ``{"person": "people", "company": "companies", "project": "projects"}``.
        When *None*, the defaults from :data:`OBJECT_TYPE_DIRS` are used.
        Pass ``config.knowledge_base.folder_map`` to use configured paths.
    """

    def __init__(self, root: Path | str, folder_map: dict[str, str] | None = None) -> None:
        self._root = Path(root)
        if folder_map is not None:
            # folder_map is type→dir; build both directions
            self._type_to_dir: dict[str, str] = dict(folder_map)
            self._dir_to_type: dict[str, str] = {v: k for k, v in folder_map.items()}
        else:
            self._type_to_dir = {v: k for k, v in OBJECT_TYPE_DIRS.items()}
            self._dir_to_type = dict(OBJECT_TYPE_DIRS)

    @property
    def root(self) -> Path:
        return self._root

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def read_file(self, file_path: Path) -> ParsedDocument:
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
            If the file is not located inside a recognised object-type
            sub-directory (``people/``, ``companies/``, ``projects/``).
        """
        file_path = Path(file_path)
        if not file_path.exists():
            logger.error("Markdown file not found: %s", file_path)
            raise FileNotFoundError(f"Markdown file not found: {file_path}")

        object_type = self._detect_object_type(file_path)
        logger.debug("Reading %s file: %s", object_type, file_path.name)
        post = frontmatter.load(str(file_path))
        doc = ParsedDocument(
            path=file_path,
            object_type=object_type,
            metadata=dict(post.metadata),
            content=post.content,
        )
        logger.debug("Parsed %s: %d front-matter key(s)", file_path.name, len(doc.metadata))
        return doc

    def read_all(self, object_type: str | None = None) -> list[ParsedDocument]:
        """Read all markdown files from the KB.

        Parameters
        ----------
        object_type:
            When supplied, only files from the matching sub-directory are
            returned.  Accepted values: ``"person"``, ``"company"``,
            ``"project"``.  When ``None``, all types are returned.

        Returns
        -------
        list[ParsedDocument]
            One entry per ``.md`` file found.
        """
        filter_msg = f" (type={object_type!r})" if object_type else ""
        logger.info("Reading Knowledge Base from %s%s", self._root, filter_msg)
        docs: list[ParsedDocument] = []
        for otype, dir_name in self._type_to_dir.items():
            if object_type and otype != object_type:
                continue
            type_dir = self._root / dir_name
            if not type_dir.is_dir():
                logger.debug("KB sub-directory not found, skipping: %s", type_dir)
                continue
            for md_file in sorted(type_dir.glob("**/*.md")):
                docs.append(self.read_file(md_file))
        logger.info("Knowledge Base read complete: %d document(s) loaded", len(docs))
        return docs

    def list_files(self, object_type: str | None = None) -> list[Path]:
        """Return paths of all ``.md`` files without parsing them.

        Parameters
        ----------
        object_type:
            When supplied, restrict to the sub-directory for that type.
        """
        paths: list[Path] = []
        for otype, dir_name in self._type_to_dir.items():
            if object_type and otype != object_type:
                continue
            type_dir = self._root / dir_name
            if not type_dir.is_dir():
                continue
            paths.extend(sorted(type_dir.glob("**/*.md")))
        return paths

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _detect_object_type(self, file_path: Path) -> str:
        """Infer the canonical object type from the file's parent directory."""
        try:
            relative = file_path.relative_to(self._root)
        except ValueError:
            relative = file_path
        top_dir = relative.parts[0] if relative.parts else ""
        if top_dir in self._dir_to_type:
            return self._dir_to_type[top_dir]
        raise ValueError(
            f"Cannot determine object type for '{file_path}'. "
            f"Expected file to be under one of: {sorted(self._dir_to_type)}"
        )
