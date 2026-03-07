"""End-to-end pipeline that reads markdown files from the Knowledge Base
and loads them into the in-memory (or DB-backed) repositories.

This is the primary ETL entry-point for the data platform:

1. **Extract** – walk KB sub-directories and parse markdown files.
2. **Transform** – map front-matter + body to canonical Person / Company /
   Project objects.
3. **Load** – persist objects via the repository layer.

Usage::

    from pathlib import Path

    from data_platform.etl.markdown_loader import MarkdownETLPipeline
    from data_platform.knowledge_base.reader import KnowledgeBaseReader
    from data_platform.repositories.people import PeopleRepository
    from data_platform.repositories.companies import CompanyRepository
    from data_platform.repositories.projects import ProjectRepository
    from data_platform.etl.loaders import RepositoryLoader

    pipeline = MarkdownETLPipeline(
        reader=KnowledgeBaseReader(Path("/kb")),
        loader=RepositoryLoader(
            people_repo=PeopleRepository(),
            companies_repo=CompanyRepository(),
            projects_repo=ProjectRepository(),
        ),
    )
    result = pipeline.run()
    print(result)
"""

from __future__ import annotations

from typing import Any

from data_platform.etl.base import ETLPipeline
from data_platform.etl.loaders import RepositoryLoader
from data_platform.etl.transformers import (
    CompanyTransformer,
    PersonTransformer,
    ProjectTransformer,
    RawDocument,
)
from data_platform.knowledge_base.reader import KnowledgeBaseReader, ParsedDocument


class MarkdownETLPipeline(ETLPipeline):
    """ETL pipeline that reads the markdown Knowledge Base into repositories.

    Parameters
    ----------
    reader:
        :class:`~data_platform.knowledge_base.reader.KnowledgeBaseReader`
        instance pointing at the KB root.
    loader:
        :class:`~data_platform.etl.loaders.RepositoryLoader` with the target
        repositories injected.
    object_type:
        When supplied, restrict the run to a single type
        (``"person"``, ``"company"``, or ``"project"``).
        Defaults to ``None`` (all types).
    """

    _TRANSFORMERS = {
        "person": PersonTransformer(),
        "company": CompanyTransformer(),
        "project": ProjectTransformer(),
    }

    def __init__(
        self,
        reader: KnowledgeBaseReader,
        loader: RepositoryLoader,
        object_type: str | None = None,
        name: str = "MarkdownETLPipeline",
    ) -> None:
        super().__init__(name=name)
        self._reader = reader
        self._loader = loader
        self._object_type = object_type

    # ------------------------------------------------------------------
    # ETLPipeline implementation
    # ------------------------------------------------------------------

    def extract(self) -> list[ParsedDocument]:
        """Walk the KB directories and return all parsed documents."""
        return self._reader.read_all(object_type=self._object_type)

    def transform(
        self, raw_records: list[ParsedDocument]
    ) -> tuple[list[Any], list[tuple[str, str]]]:
        """Convert :class:`ParsedDocument` instances to canonical objects."""
        all_objects: list[Any] = []
        all_errors: list[tuple[str, str]] = []

        for doc in raw_records:
            transformer = self._TRANSFORMERS.get(doc.object_type)
            if transformer is None:
                all_errors.append((str(doc.path), f"Unknown object type: {doc.object_type!r}"))
                continue
            raw = RawDocument.from_parsed(doc)
            try:
                obj = transformer.transform(raw)
                all_objects.append(obj)
            except Exception as exc:
                all_errors.append((str(doc.path), str(exc)))

        return all_objects, all_errors

    def load(self, objects: list[Any]) -> int:
        """Persist canonical objects via the :class:`RepositoryLoader`."""
        return self._loader.load(objects)
