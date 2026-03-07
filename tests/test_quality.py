"""Tests for data_platform.quality – checks and lineage."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from data_platform.ontology_adapter import Company, Person, Project
from data_platform.quality.checks import (
    DataQualityReport,
    NoNullNamesCheck,
    RequiredFieldsCheck,
    TagsFormatCheck,
    UniqueIdCheck,
    run_checks,
)
from data_platform.quality.lineage import LineageRecord, LineageTracker


# ---------------------------------------------------------------------------
# Quality Checks
# ---------------------------------------------------------------------------


class TestRequiredFieldsCheck:
    def test_passes_when_all_present(self):
        people = [Person(id="p1", name="Alice", email="a@b.com")]
        result = RequiredFieldsCheck(["name", "email"]).run(people)
        assert result.passed
        assert len(result.violations) == 0

    def test_fails_on_missing_field(self):
        people = [Person(id="p1", name="Alice")]  # no email
        result = RequiredFieldsCheck(["name", "email"]).run(people)
        assert not result.passed
        assert any("email" in v for v in result.violations)

    def test_fails_on_empty_string_field(self):
        people = [Person(id="p1", name="")]
        result = RequiredFieldsCheck(["name"]).run(people)
        assert not result.passed

    def test_multiple_missing(self):
        people = [Person(id="p1", name="Alice"), Person(id="p2", name="")]
        result = RequiredFieldsCheck(["name"]).run(people)
        assert not result.passed
        assert len(result.violations) == 1  # only p2

    def test_name(self):
        check = RequiredFieldsCheck(["name", "email"])
        assert "name" in check.name and "email" in check.name


class TestUniqueIdCheck:
    def test_passes_on_unique_ids(self):
        people = [
            Person(id="p1", name="Alice"),
            Person(id="p2", name="Bob"),
        ]
        result = UniqueIdCheck().run(people)
        assert result.passed

    def test_fails_on_duplicate_id(self):
        people = [
            Person(id="p1", name="Alice"),
            Person(id="p1", name="Alice Clone"),
        ]
        result = UniqueIdCheck().run(people)
        assert not result.passed
        assert any("p1" in v for v in result.violations)

    def test_empty_list_passes(self):
        assert UniqueIdCheck().run([]).passed


class TestNoNullNamesCheck:
    def test_passes(self):
        people = [Person(id="p1", name="Alice")]
        assert NoNullNamesCheck().run(people).passed

    def test_fails_on_blank_name(self):
        people = [Person(id="p1", name="  ")]
        result = NoNullNamesCheck().run(people)
        assert not result.passed


class TestTagsFormatCheck:
    def test_passes_on_list(self):
        people = [Person(id="p1", name="Alice", tags=["python"])]
        assert TagsFormatCheck().run(people).passed

    def test_passes_on_empty_list(self):
        people = [Person(id="p1", name="Alice", tags=[])]
        assert TagsFormatCheck().run(people).passed

    def test_fails_on_non_list(self):
        # Bypass pydantic validation by injecting into a dict-constructed object
        # Use a Company with no tags field manipulation – instead test via metadata dict
        # We test the check logic directly by passing an object with .tags = "bad"
        class FakeRecord:
            id = "x1"
            tags = "not-a-list"

        result = TagsFormatCheck().run([FakeRecord()])
        assert not result.passed


class TestRunChecks:
    def test_run_multiple_checks(self):
        people = [Person(id="p1", name="Alice", email="alice@example.com")]
        report = run_checks(
            people,
            checks=[RequiredFieldsCheck(["name", "email"]), UniqueIdCheck()],
        )
        assert report.passed
        assert len(report.results) == 2

    def test_report_failed_checks(self):
        people = [Person(id="p1", name=""), Person(id="p1", name="Clone")]
        report = run_checks(
            people,
            checks=[RequiredFieldsCheck(["name"]), UniqueIdCheck()],
        )
        assert not report.passed
        failed = report.failed_checks()
        assert len(failed) >= 1

    def test_summary_contains_pass_fail(self):
        people = [Person(id="p1", name="Alice")]
        report = run_checks(people, checks=[UniqueIdCheck()])
        summary = report.summary()
        assert "PASS" in summary or "FAIL" in summary

    def test_total_violations(self):
        people = [Person(id="p1", name=""), Person(id="p1", name="Clone")]
        report = run_checks(people, checks=[RequiredFieldsCheck(["name"]), UniqueIdCheck()])
        assert report.total_violations >= 2


class TestDataQualityReport:
    def test_passed_when_no_results(self):
        report = DataQualityReport()
        assert report.passed  # vacuously true

    def test_failed_when_any_fails(self):
        from data_platform.quality.checks import QualityCheckResult

        report = DataQualityReport(
            results=[QualityCheckResult(check_name="test", passed=False, violations=["oops"])]
        )
        assert not report.passed


# ---------------------------------------------------------------------------
# Lineage Tracker
# ---------------------------------------------------------------------------


class TestLineageTracker:
    def test_record_and_retrieve(self):
        tracker = LineageTracker()
        rec = tracker.record(
            object_id="p1",
            object_type="person",
            source="people/alice.md",
            pipeline="MarkdownETLPipeline",
        )
        assert isinstance(rec, LineageRecord)
        history = tracker.get_history("p1")
        assert len(history) == 1
        assert history[0].source == "people/alice.md"

    def test_get_all(self):
        tracker = LineageTracker()
        tracker.record("p1", "person", "file1.md", "pipe1")
        tracker.record("c1", "company", "file2.md", "pipe1")
        assert len(tracker.get_all()) == 2

    def test_get_by_pipeline(self):
        tracker = LineageTracker()
        tracker.record("p1", "person", "f1.md", "pipe1")
        tracker.record("c1", "company", "f2.md", "pipe2")
        results = tracker.get_by_pipeline("pipe1")
        assert len(results) == 1

    def test_get_by_source(self):
        tracker = LineageTracker()
        tracker.record("p1", "person", "people/alice.md", "pipe1")
        tracker.record("p2", "person", "people/bob.md", "pipe1")
        results = tracker.get_by_source("people/alice.md")
        assert len(results) == 1

    def test_record_etl_result(self):
        tracker = LineageTracker()
        objects = [
            Person(id="p1", name="Alice"),
            Company(id="c1", name="Acme"),
        ]
        records = tracker.record_etl_result(objects, source="kb", pipeline="pipe")
        assert len(records) == 2
        assert tracker.summary()["total_records"] == 2

    def test_summary(self):
        tracker = LineageTracker()
        tracker.record("p1", "person", "f.md", "pipe1")
        tracker.record("c1", "company", "g.md", "pipe1")
        summary = tracker.summary()
        assert summary["total_records"] == 2
        assert summary["by_object_type"]["person"] == 1
        assert summary["by_pipeline"]["pipe1"] == 2

    def test_lineage_record_to_dict(self):
        rec = LineageRecord(
            object_id="p1",
            object_type="person",
            source="f.md",
            pipeline="pipe",
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        d = rec.to_dict()
        assert d["object_id"] == "p1"
        assert "timestamp" in d

    def test_metadata_stored(self):
        tracker = LineageTracker()
        rec = tracker.record("p1", "person", "f.md", "pipe", row_count=10)
        assert rec.metadata["row_count"] == 10
