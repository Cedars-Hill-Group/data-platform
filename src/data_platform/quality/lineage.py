"""Data lineage metadata tracking.

Records where each canonical object came from (source file, pipeline,
timestamp) and allows querying the lineage history.

Example::

    from data_platform.quality.lineage import LineageTracker

    tracker = LineageTracker()
    tracker.record(
        object_id="abc-123",
        object_type="person",
        source="people/alice-smith.md",
        pipeline="MarkdownETLPipeline",
    )

    history = tracker.get_history("abc-123")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from data_platform.log import get_logger

logger = get_logger(__name__)


@dataclass
class LineageRecord:
    """A single lineage event for one canonical object.

    Attributes
    ----------
    object_id:
        ID of the canonical object this record belongs to.
    object_type:
        Canonical type (``"person"``, ``"company"``, ``"project"``).
    source:
        Human-readable description of the data source (file path, URL, etc.).
    pipeline:
        Name of the ETL pipeline that produced the transformation.
    operation:
        Type of operation: ``"extract"``, ``"transform"``, ``"load"``, or
        ``"create"`` / ``"update"`` for KB writes.
    timestamp:
        UTC datetime when the event was recorded.
    metadata:
        Arbitrary extra context (e.g. row counts, schema versions).
    """

    object_id: str
    object_type: str
    source: str
    pipeline: str
    operation: str = "load"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "object_id": self.object_id,
            "object_type": self.object_type,
            "source": self.source,
            "pipeline": self.pipeline,
            "operation": self.operation,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


class LineageTracker:
    """Accumulates and queries lineage records for canonical objects.

    The default implementation stores records in memory.  For persistence,
    subclass and override :meth:`record` / :meth:`get_history` to write to a
    database or event log.
    """

    def __init__(self) -> None:
        self._records: list[LineageRecord] = []

    def record(
        self,
        object_id: str,
        object_type: str,
        source: str,
        pipeline: str,
        operation: str = "load",
        **metadata: Any,
    ) -> LineageRecord:
        """Create and store a new lineage record.

        Parameters
        ----------
        object_id:
            ID of the affected canonical object.
        object_type:
            Canonical type string (``"person"``, etc.).
        source:
            Source identifier (file path, URL, dataset name, …).
        pipeline:
            Pipeline / process that triggered the event.
        operation:
            Operation type (default: ``"load"``).
        **metadata:
            Arbitrary extra key/value pairs stored in the record's metadata.

        Returns
        -------
        LineageRecord
            The newly created record.
        """
        rec = LineageRecord(
            object_id=object_id,
            object_type=object_type,
            source=source,
            pipeline=pipeline,
            operation=operation,
            metadata=dict(metadata),
        )
        self._records.append(rec)
        logger.debug(
            "Lineage recorded: object_id=%s type=%s pipeline=%s operation=%s source=%s",
            object_id,
            object_type,
            pipeline,
            operation,
            source,
        )
        return rec

    def get_history(self, object_id: str) -> list[LineageRecord]:
        """Return all lineage records for *object_id*, oldest first."""
        return [r for r in self._records if r.object_id == object_id]

    def get_all(self) -> list[LineageRecord]:
        """Return every recorded lineage event."""
        return list(self._records)

    def get_by_pipeline(self, pipeline: str) -> list[LineageRecord]:
        """Return all records produced by *pipeline*."""
        return [r for r in self._records if r.pipeline == pipeline]

    def get_by_source(self, source: str) -> list[LineageRecord]:
        """Return all records originating from *source*."""
        return [r for r in self._records if r.source == source]

    def record_etl_result(
        self,
        objects: list[Any],
        source: str,
        pipeline: str,
        operation: str = "load",
    ) -> list[LineageRecord]:
        """Batch-record lineage for a list of canonical objects.

        Parameters
        ----------
        objects:
            Canonical model instances (must have ``id`` and the class name
            is used as the ``object_type``).
        source:
            Data source description.
        pipeline:
            Pipeline name.
        operation:
            Operation type (default ``"load"``).

        Returns
        -------
        list[LineageRecord]
            Newly created records.
        """
        records = []
        for obj in objects:
            obj_id = getattr(obj, "id", str(id(obj)))
            obj_type = type(obj).__name__.lower()
            records.append(self.record(obj_id, obj_type, source, pipeline, operation))
        logger.info(
            "Lineage batch recorded: %d record(s) for pipeline=%s operation=%s",
            len(records),
            pipeline,
            operation,
        )
        return records

    def summary(self) -> dict[str, Any]:
        """Return a high-level summary of recorded lineage."""
        by_type: dict[str, int] = {}
        by_pipeline: dict[str, int] = {}
        for r in self._records:
            by_type[r.object_type] = by_type.get(r.object_type, 0) + 1
            by_pipeline[r.pipeline] = by_pipeline.get(r.pipeline, 0) + 1
        return {
            "total_records": len(self._records),
            "by_object_type": by_type,
            "by_pipeline": by_pipeline,
        }
