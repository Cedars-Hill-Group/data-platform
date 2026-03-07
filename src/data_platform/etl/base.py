"""Abstract base ETL pipeline and result container."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ETLResult:
    """Summary of a single ETL pipeline run.

    Attributes
    ----------
    pipeline_name:
        Human-readable name of the pipeline that produced this result.
    records_extracted:
        Number of raw records read from the source.
    records_transformed:
        Number of records successfully mapped to canonical objects.
    records_loaded:
        Number of records written to the target repository / store.
    errors:
        List of (record_id, error_message) tuples for failures encountered
        during transformation or loading.
    metadata:
        Arbitrary pipeline-specific metadata (timing, source paths, etc.).
    """

    pipeline_name: str
    records_extracted: int = 0
    records_transformed: int = 0
    records_loaded: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        """Fraction of extracted records that were loaded (0.0–1.0)."""
        if self.records_extracted == 0:
            return 1.0
        return self.records_loaded / self.records_extracted

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    def __str__(self) -> str:
        return (
            f"{self.pipeline_name}: "
            f"extracted={self.records_extracted}, "
            f"transformed={self.records_transformed}, "
            f"loaded={self.records_loaded}, "
            f"errors={len(self.errors)}"
        )


class ETLPipeline(ABC):
    """Base class for all ETL/ELT pipelines.

    Subclasses implement :meth:`extract`, :meth:`transform`, and
    :meth:`load`.  The :meth:`run` method orchestrates the full pipeline and
    returns an :class:`ETLResult`.

    Parameters
    ----------
    name:
        Human-readable pipeline identifier used in logs and result objects.
    """

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def extract(self) -> list[Any]:
        """Read raw data from the source and return a list of raw records."""

    @abstractmethod
    def transform(self, raw_records: list[Any]) -> tuple[list[Any], list[tuple[str, str]]]:
        """Map raw records to canonical objects.

        Returns
        -------
        tuple[list[Any], list[tuple[str, str]]]
            ``(canonical_objects, errors)`` where *errors* is a list of
            ``(record_id, message)`` tuples.
        """

    @abstractmethod
    def load(self, objects: list[Any]) -> int:
        """Persist canonical objects to the target store.

        Returns
        -------
        int
            Number of records successfully written.
        """

    def run(self) -> ETLResult:
        """Execute extract → transform → load and return a summary result."""
        result = ETLResult(pipeline_name=self.name)

        raw_records = self.extract()
        result.records_extracted = len(raw_records)

        canonical_objects, errors = self.transform(raw_records)
        result.records_transformed = len(canonical_objects)
        result.errors.extend(errors)

        loaded = self.load(canonical_objects)
        result.records_loaded = loaded

        return result
