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


# Map canonical type name → sub-directory.
# ``"property"`` is the current canonical type; ``"project"`` is retained as a
# backward-compatible alias pointing to the same ``Properties/`` folder.
_TYPE_TO_DIR: dict[str, str] = {
    "person": "people",
    "company": "companies",
    "property": "Properties",
    # Backward-compatible alias.
    "project": "Properties",
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
        e.g. ``{"person": "people", "company": "companies", "property": "Properties"}``.
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
            One of ``"person"``, ``"company"``, ``"property"``
            (``"project"`` is also accepted for backward compatibility).
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

        # Determine object type from parent dir name.
        # Build reverse map, but prefer "property" over the legacy "project" alias.
        parent_name = file_path.parent.name
        reverse_map: dict[str, str] = {}
        for type_key, dir_name in self._type_to_dir.items():
            # Only overwrite an existing entry if the new key is not a legacy alias.
            if dir_name not in reverse_map or type_key != "project":
                reverse_map[dir_name] = type_key
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
        file_path = Path(file_path)
        if not file_path.exists():
            logger.error("Cannot delete – file not found: %s", file_path)
            raise FileNotFoundError(f"File not found: {file_path}")
        file_path.unlink()
        logger.info("Deleted KB file: %s", file_path)

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
        """Write *content* under a specific markdown *header*.

        When the header exists, its section body is replaced. When missing and
        *create_if_missing* is ``True``, the header and content are appended.
        """
        return self.write_header_sections(
            file_path,
            {header: content},
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
        """Write content for one or more markdown header sections.

        Parameters
        ----------
        file_path:
            Markdown file to update.
        sections:
            Mapping of header title to section body text.
        create_if_missing:
            Create missing headers when ``True``.
        header_level:
            Header level to use for newly created sections (1..6).
        case_sensitive:
            Whether header matching is case-sensitive.
        normalize:
            Whether to normalize header labels during matching.
        """
        import frontmatter  # noqa: PLC0415

        file_path = Path(file_path)
        if not file_path.exists():
            logger.error("Cannot update header sections - file not found: %s", file_path)
            raise FileNotFoundError(f"File not found: {file_path}")
        if not sections:
            return file_path
        if not 1 <= header_level <= 6:
            raise ValueError("header_level must be between 1 and 6")

        post = frontmatter.load(str(file_path))
        updated_body = self._write_sections_in_markdown(
            post.content,
            sections,
            create_if_missing=create_if_missing,
            header_level=header_level,
            case_sensitive=case_sensitive,
            normalize=normalize,
        )
        post.content = updated_body
        file_path.write_text(frontmatter.dumps(post), encoding="utf-8")
        logger.info("Updated %d header section(s) in file: %s", len(sections), file_path)
        return file_path

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
        """Append *content* under a specific markdown *header*."""
        return self.append_header_sections(
            file_path,
            {header: content},
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
        """Append content to one or more markdown header sections.

        Existing section content is preserved and the new content is appended
        separated by a blank line. Missing headers are optionally created.
        """
        import frontmatter  # noqa: PLC0415

        file_path = Path(file_path)
        if not file_path.exists():
            logger.error("Cannot append header sections - file not found: %s", file_path)
            raise FileNotFoundError(f"File not found: {file_path}")
        if not sections:
            return file_path
        if not 1 <= header_level <= 6:
            raise ValueError("header_level must be between 1 and 6")

        post = frontmatter.load(str(file_path))
        appended_body = self._write_sections_in_markdown(
            post.content,
            sections,
            create_if_missing=create_if_missing,
            header_level=header_level,
            case_sensitive=case_sensitive,
            normalize=normalize,
            mode="append",
        )
        post.content = appended_body
        file_path.write_text(frontmatter.dumps(post), encoding="utf-8")
        logger.info("Appended to %d header section(s) in file: %s", len(sections), file_path)
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

    @staticmethod
    def _write_sections_in_markdown(
        markdown: str,
        sections: dict[str, str],
        *,
        create_if_missing: bool,
        header_level: int,
        case_sensitive: bool,
        normalize: bool,
        mode: str = "replace",
    ) -> str:
        """Return markdown with selected section bodies replaced/created."""
        if mode not in {"replace", "append"}:
            raise ValueError("mode must be 'replace' or 'append'")
        header_pattern = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
        lines = markdown.splitlines()
        header_nodes: list[tuple[int, int, str]] = []
        for line_number, line in enumerate(lines):
            match = header_pattern.match(line)
            if not match:
                continue
            level = len(match.group(1))
            title = match.group(2).strip()
            header_nodes.append((line_number, level, title))

        section_ranges: dict[str, list[tuple[int, int]]] = {}
        for index, (line_number, level, title) in enumerate(header_nodes):
            section_end = len(lines)
            for next_line, next_level, _ in header_nodes[index + 1 :]:
                if next_level <= level:
                    section_end = next_line
                    break
            section_ranges.setdefault(title, []).append((line_number + 1, section_end))

        key_to_titles: dict[str, list[str]] = {}
        for _, _, title in header_nodes:
            key = KnowledgeBaseWriter._header_match_key(
                title,
                case_sensitive=case_sensitive,
                normalize=normalize,
            )
            key_to_titles.setdefault(key, []).append(title)

        # Apply replacements from bottom to top so line indexes stay valid.
        replacements: list[tuple[int, int, list[str]]] = []
        to_append: list[tuple[str, str]] = []
        for requested_header, body in sections.items():
            requested_key = KnowledgeBaseWriter._header_match_key(
                requested_header,
                case_sensitive=case_sensitive,
                normalize=normalize,
            )
            matched_titles = key_to_titles.get(requested_key, [])
            if not matched_titles:
                if create_if_missing:
                    to_append.append((requested_header.strip(), body.strip()))
                    continue
                raise ValueError(
                    f"Header not found: '{requested_header}'. "
                    "Pass create_if_missing=True to append it."
                )

            body_lines = body.strip().splitlines()
            for matched_title in matched_titles:
                for start, end in section_ranges.get(matched_title, []):
                    if mode == "replace":
                        new_lines = body_lines
                    else:
                        existing_lines = lines[start:end]
                        existing_block = "\n".join(existing_lines).strip()
                        append_block = body.strip()
                        if existing_block and append_block:
                            merged_block = f"{existing_block}\n\n{append_block}"
                        else:
                            merged_block = existing_block or append_block
                        new_lines = merged_block.splitlines()
                    replacements.append((start, end, new_lines))

        for start, end, new_lines in sorted(replacements, key=lambda item: item[0], reverse=True):
            lines[start:end] = new_lines

        updated = "\n".join(lines).strip("\n")
        if to_append:
            append_parts: list[str] = []
            for title, body in to_append:
                append_parts.append(f"{'#' * header_level} {title}")
                if body:
                    append_parts.append(body)
            append_block = "\n\n".join(append_parts).strip("\n")
            if updated:
                updated = f"{updated}\n\n{append_block}"
            else:
                updated = append_block
        return updated + "\n"

    @staticmethod
    def _header_match_key(header: str, *, case_sensitive: bool, normalize: bool) -> str:
        key = header.strip()
        if normalize:
            key = re.sub(r"\s+", " ", key)
            key = key.strip("#")
            key = key.strip(" \t-_:;,.!?\"'`()[]{}")
        if not case_sensitive:
            key = key.casefold()
        return key
