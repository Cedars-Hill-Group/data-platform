"""Data quality checks for canonical ontology objects.

Checks are composable and can be run against any list of pydantic model
instances.  Each check returns a :class:`QualityCheckResult` describing pass /
fail status and any violations found.

Example::

    from data_platform.quality.checks import RequiredFieldsCheck, UniqueIdCheck, run_checks
    from data_platform.repositories.people import PeopleRepository

    repo = PeopleRepository()
    people = repo.list()

    report = run_checks(
        records=people,
        checks=[RequiredFieldsCheck(["name", "email"]), UniqueIdCheck()],
    )
    print(report.summary())
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from data_platform.log import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Result / Report containers
# ---------------------------------------------------------------------------


@dataclass
class QualityCheckResult:
    """Result of a single quality check.

    Attributes
    ----------
    check_name:
        Name of the check that produced this result.
    passed:
        ``True`` when the check found no violations.
    violations:
        List of human-readable violation descriptions.
    """

    check_name: str
    passed: bool
    violations: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"[{status}] {self.check_name}: {len(self.violations)} violation(s)"


@dataclass
class DataQualityReport:
    """Aggregated results from running multiple quality checks.

    Attributes
    ----------
    results:
        Individual :class:`QualityCheckResult` objects.
    """

    results: list[QualityCheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """``True`` when every individual check passed."""
        return all(r.passed for r in self.results)

    @property
    def total_violations(self) -> int:
        return sum(len(r.violations) for r in self.results)

    def summary(self) -> str:
        lines = [
            f"Data Quality Report – {'PASS' if self.passed else 'FAIL'}",
            f"  Checks run: {len(self.results)}",
            f"  Total violations: {self.total_violations}",
        ]
        for result in self.results:
            lines.append(f"  {result}")
            for v in result.violations:
                lines.append(f"    • {v}")
        return "\n".join(lines)

    def failed_checks(self) -> list[QualityCheckResult]:
        """Return only the checks that failed."""
        return [r for r in self.results if not r.passed]


# ---------------------------------------------------------------------------
# Abstract check interface
# ---------------------------------------------------------------------------


class DataQualityCheck(ABC):
    """Base class for all data quality checks."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable check name."""

    @abstractmethod
    def run(self, records: list[Any]) -> QualityCheckResult:
        """Execute the check against *records* and return a result."""


# ---------------------------------------------------------------------------
# Built-in checks
# ---------------------------------------------------------------------------


class RequiredFieldsCheck(DataQualityCheck):
    """Verify that required fields are non-null and non-empty.

    Parameters
    ----------
    required_fields:
        List of field names that must be present and non-empty on every record.
    """

    def __init__(self, required_fields: list[str]) -> None:
        self._required = required_fields

    @property
    def name(self) -> str:
        return f"RequiredFields({', '.join(self._required)})"

    def run(self, records: list[Any]) -> QualityCheckResult:
        violations: list[str] = []
        for record in records:
            record_id = getattr(record, "id", repr(record))
            for field_name in self._required:
                value = getattr(record, field_name, None)
                if value is None or (isinstance(value, str) and not value.strip()):
                    violations.append(
                        f"Record '{record_id}' missing required field '{field_name}'"
                    )
        return QualityCheckResult(
            check_name=self.name,
            passed=len(violations) == 0,
            violations=violations,
        )


class UniqueIdCheck(DataQualityCheck):
    """Verify that every record has a unique ``id`` field.

    Records without an ``id`` attribute are also reported.
    """

    @property
    def name(self) -> str:
        return "UniqueId"

    def run(self, records: list[Any]) -> QualityCheckResult:
        violations: list[str] = []
        seen: dict[str, int] = {}
        for i, record in enumerate(records):
            record_id = getattr(record, "id", None)
            if record_id is None:
                violations.append(f"Record at index {i} has no 'id' field")
                continue
            if record_id in seen:
                violations.append(
                    f"Duplicate id '{record_id}' found at indices {seen[record_id]} and {i}"
                )
            else:
                seen[record_id] = i
        return QualityCheckResult(
            check_name=self.name,
            passed=len(violations) == 0,
            violations=violations,
        )


class NoNullNamesCheck(DataQualityCheck):
    """Verify that no record has a null or blank ``name`` field."""

    @property
    def name(self) -> str:
        return "NoNullNames"

    def run(self, records: list[Any]) -> QualityCheckResult:
        violations: list[str] = []
        for record in records:
            record_id = getattr(record, "id", repr(record))
            name = getattr(record, "name", None)
            if not name or not str(name).strip():
                violations.append(f"Record '{record_id}' has a null or blank name")
        return QualityCheckResult(
            check_name=self.name,
            passed=len(violations) == 0,
            violations=violations,
        )


class TagsFormatCheck(DataQualityCheck):
    """Verify that the ``tags`` field is a list of strings (not None)."""

    @property
    def name(self) -> str:
        return "TagsFormat"

    def run(self, records: list[Any]) -> QualityCheckResult:
        violations: list[str] = []
        for record in records:
            record_id = getattr(record, "id", repr(record))
            tags = getattr(record, "tags", None)
            if tags is None:
                violations.append(f"Record '{record_id}' has None tags (expected list)")
            elif not isinstance(tags, list):
                violations.append(
                    f"Record '{record_id}' tags is {type(tags).__name__} (expected list)"
                )
        return QualityCheckResult(
            check_name=self.name,
            passed=len(violations) == 0,
            violations=violations,
        )


# ---------------------------------------------------------------------------
# Runner helper
# ---------------------------------------------------------------------------


def run_checks(
    records: list[Any],
    checks: list[DataQualityCheck],
) -> DataQualityReport:
    """Run all *checks* against *records* and return a combined report.

    Parameters
    ----------
    records:
        List of canonical model instances to validate.
    checks:
        Quality checks to apply.

    Returns
    -------
    DataQualityReport
        Aggregated report with results from every check.
    """
    logger.info(
        "Running %d data quality check(s) against %d record(s)",
        len(checks),
        len(records),
    )
    report = DataQualityReport()
    for check in checks:
        result = check.run(records)
        report.results.append(result)
        if result.passed:
            logger.debug("Check '%s': PASS", check.name)
        else:
            logger.warning(
                "Check '%s': FAIL – %d violation(s)",
                check.name,
                len(result.violations),
            )
            for violation in result.violations:
                logger.debug("  violation: %s", violation)

    status = "PASS" if report.passed else "FAIL"
    logger.info(
        "Data quality run complete: %s – %d check(s), %d total violation(s)",
        status,
        len(report.results),
        report.total_violations,
    )
    return report
