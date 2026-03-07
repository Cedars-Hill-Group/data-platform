"""Tests for data_platform.log – central logging configuration."""

from __future__ import annotations

import json
import logging
import sys
from io import StringIO
from pathlib import Path

import pytest

from data_platform.log import (
    LOGGER_NAME,
    _JsonFormatter,
    _TextFormatter,
    configure_logging,
    get_logger,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _capture_handler(level: str = "DEBUG") -> tuple[logging.Logger, StringIO]:
    """Return (logger, stream) with a StringIO handler attached."""
    root = logging.getLogger(LOGGER_NAME)
    root.handlers.clear()
    buf = StringIO()
    handler = logging.StreamHandler(buf)
    handler.setLevel(getattr(logging, level.upper()))
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    return root, buf


# ---------------------------------------------------------------------------
# get_logger
# ---------------------------------------------------------------------------


class TestGetLogger:
    def test_returns_logger_instance(self):
        logger = get_logger(__name__)
        assert isinstance(logger, logging.Logger)

    def test_name_already_prefixed(self):
        logger = get_logger("data_platform.something")
        assert logger.name == "data_platform.something"

    def test_name_without_prefix_gets_prefixed(self):
        logger = get_logger("mymodule")
        assert logger.name == "data_platform.mymodule"

    def test_root_name_not_double_prefixed(self):
        logger = get_logger(LOGGER_NAME)
        assert logger.name == LOGGER_NAME

    def test_child_loggers_share_root(self):
        child = get_logger("child_a")
        # All children have `data_platform` as ultimate ancestor
        assert child.name.startswith(LOGGER_NAME)


# ---------------------------------------------------------------------------
# configure_logging
# ---------------------------------------------------------------------------


class TestConfigureLogging:
    def teardown_method(self):
        # Reset after each test to avoid handler leaks
        root = logging.getLogger(LOGGER_NAME)
        root.handlers.clear()
        root.propagate = False

    def test_default_level_is_info(self):
        configure_logging()
        root = logging.getLogger(LOGGER_NAME)
        assert root.level == logging.INFO

    def test_custom_level_debug(self):
        configure_logging(level="DEBUG")
        root = logging.getLogger(LOGGER_NAME)
        assert root.level == logging.DEBUG

    def test_custom_level_warning(self):
        configure_logging(level="WARNING")
        root = logging.getLogger(LOGGER_NAME)
        assert root.level == logging.WARNING

    def test_unknown_level_falls_back_to_info(self):
        configure_logging(level="NOTEXIST")
        root = logging.getLogger(LOGGER_NAME)
        # getattr fallback returns INFO (logging.INFO == 20)
        assert root.level == logging.INFO

    def test_adds_stream_handler(self):
        configure_logging()
        root = logging.getLogger(LOGGER_NAME)
        assert any(isinstance(h, logging.StreamHandler) for h in root.handlers)

    def test_idempotent_reconfiguration_replaces_handlers(self):
        configure_logging(level="INFO")
        configure_logging(level="DEBUG")
        root = logging.getLogger(LOGGER_NAME)
        # Should not accumulate handlers
        assert len(root.handlers) == 1

    def test_does_not_propagate(self):
        configure_logging()
        root = logging.getLogger(LOGGER_NAME)
        assert root.propagate is False

    def test_json_logs_flag(self):
        configure_logging(json_logs=True)
        root = logging.getLogger(LOGGER_NAME)
        assert any(isinstance(h.formatter, _JsonFormatter) for h in root.handlers)

    def test_text_logs_flag(self):
        configure_logging(json_logs=False)
        root = logging.getLogger(LOGGER_NAME)
        assert any(isinstance(h.formatter, _TextFormatter) for h in root.handlers)

    def test_log_file_creates_file_handler(self, tmp_path: Path):
        log_path = tmp_path / "test.log"
        configure_logging(log_file=str(log_path))
        root = logging.getLogger(LOGGER_NAME)
        file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 1
        # Clean up
        for h in file_handlers:
            h.close()

    def test_log_file_writes_output(self, tmp_path: Path):
        log_path = tmp_path / "output.log"
        configure_logging(level="DEBUG", log_file=str(log_path))
        logger = get_logger("test_file_output")
        logger.info("hello from file logger")
        # Flush file handler
        for h in logging.getLogger(LOGGER_NAME).handlers:
            h.flush()
            if isinstance(h, logging.FileHandler):
                h.close()
        assert log_path.exists()
        assert "hello from file logger" in log_path.read_text()

    def test_stdout_output_captured(self, capsys):
        configure_logging(level="INFO")
        logger = get_logger("test_stdout")
        logger.info("stdout test message")
        captured = capsys.readouterr()
        assert "stdout test message" in captured.out


# ---------------------------------------------------------------------------
# _TextFormatter
# ---------------------------------------------------------------------------


class TestTextFormatter:
    def test_format_contains_level(self):
        formatter = _TextFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="test message", args=(), exc_info=None,
        )
        formatted = formatter.format(record)
        assert "INFO" in formatted
        assert "test message" in formatted

    def test_format_contains_logger_name(self):
        formatter = _TextFormatter()
        record = logging.LogRecord(
            name="data_platform.etl", level=logging.WARNING, pathname="", lineno=0,
            msg="warn msg", args=(), exc_info=None,
        )
        formatted = formatter.format(record)
        assert "data_platform.etl" in formatted


# ---------------------------------------------------------------------------
# _JsonFormatter
# ---------------------------------------------------------------------------


class TestJsonFormatter:
    def _make_record(self, msg: str = "hello", level: int = logging.INFO, **kwargs) -> logging.LogRecord:
        record = logging.LogRecord(
            name="data_platform.test",
            level=level,
            pathname="",
            lineno=0,
            msg=msg,
            args=(),
            exc_info=None,
        )
        for k, v in kwargs.items():
            setattr(record, k, v)
        return record

    def test_output_is_valid_json(self):
        formatter = _JsonFormatter()
        record = self._make_record("test")
        output = formatter.format(record)
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_required_fields_present(self):
        formatter = _JsonFormatter()
        record = self._make_record("hello json")
        parsed = json.loads(formatter.format(record))
        assert "timestamp" in parsed
        assert "level" in parsed
        assert "logger" in parsed
        assert "message" in parsed

    def test_message_field(self):
        formatter = _JsonFormatter()
        record = self._make_record("my json message")
        parsed = json.loads(formatter.format(record))
        assert parsed["message"] == "my json message"

    def test_level_field(self):
        formatter = _JsonFormatter()
        record = self._make_record("msg", level=logging.WARNING)
        parsed = json.loads(formatter.format(record))
        assert parsed["level"] == "WARNING"

    def test_extra_fields_included(self):
        formatter = _JsonFormatter()
        record = self._make_record("msg with extra")
        record.pipeline_name = "TestPipeline"
        parsed = json.loads(formatter.format(record))
        assert parsed.get("pipeline_name") == "TestPipeline"

    def test_exception_info_included(self):
        formatter = _JsonFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            exc_info = sys.exc_info()
        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="", lineno=0,
            msg="error occurred", args=(), exc_info=exc_info,
        )
        parsed = json.loads(formatter.format(record))
        assert "exc_info" in parsed
        assert "ValueError" in parsed["exc_info"]

    def test_single_line_output(self):
        formatter = _JsonFormatter()
        record = self._make_record("single line check")
        output = formatter.format(record)
        assert "\n" not in output


# ---------------------------------------------------------------------------
# Integration: logging emitted by platform modules
# ---------------------------------------------------------------------------


class TestLoggingIntegration:
    """Verify that platform modules emit log records via the data_platform hierarchy."""

    def _capture(self) -> tuple[logging.handlers.MemoryHandler, list[logging.LogRecord]]:
        """Add an in-memory handler directly to the data_platform logger."""
        import logging.handlers as _lh

        records: list[logging.LogRecord] = []

        class _ListHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        handler = _ListHandler()
        handler.setLevel(logging.DEBUG)
        root = logging.getLogger(LOGGER_NAME)
        root.setLevel(logging.DEBUG)
        root.addHandler(handler)
        return handler, records

    def teardown_method(self):
        root = logging.getLogger(LOGGER_NAME)
        root.handlers.clear()

    def test_config_module_emits_logs(self, config_file):
        """get_config should call configure_logging and the config logger exists."""
        from unittest.mock import patch

        from data_platform.config import get_config, reset_config_cache
        import data_platform.config as _config_mod

        reset_config_cache()
        with patch.object(_config_mod, "configure_logging") as mock_conf:
            cfg = get_config(str(config_file))
        reset_config_cache()

        # configure_logging must be called once with the loaded logging settings
        mock_conf.assert_called_once()
        call_kwargs = mock_conf.call_args
        assert call_kwargs is not None

        # The data_platform.config module logger exists in the hierarchy
        logger_obj = logging.getLogger("data_platform.config")
        assert logger_obj.name == "data_platform.config"

    def test_etl_pipeline_emits_logs(self, kb_root):
        from data_platform.etl.loaders import RepositoryLoader
        from data_platform.etl.markdown_loader import MarkdownETLPipeline
        from data_platform.knowledge_base.reader import KnowledgeBaseReader
        from data_platform.repositories.companies import CompanyRepository
        from data_platform.repositories.people import PeopleRepository
        from data_platform.repositories.projects import ProjectRepository

        handler, records = self._capture()
        pipeline = MarkdownETLPipeline(
            reader=KnowledgeBaseReader(kb_root),
            loader=RepositoryLoader(
                people_repo=PeopleRepository(),
                companies_repo=CompanyRepository(),
                projects_repo=ProjectRepository(),
            ),
        )
        pipeline.run()
        messages = [r.getMessage() for r in records]
        assert any("MarkdownETLPipeline" in m for m in messages)
        assert any("Extracted" in m for m in messages)

    def test_quality_checks_emit_logs(self):
        from data_platform.ontology_adapter import Person
        from data_platform.quality.checks import RequiredFieldsCheck, run_checks

        handler, records = self._capture()
        people = [Person(id="p1", name="Alice", email="alice@example.com")]
        run_checks(people, [RequiredFieldsCheck(["name", "email"])])
        messages = " ".join(r.getMessage() for r in records).lower()
        assert "data quality check" in messages

    def test_lineage_tracker_emits_logs(self):
        from data_platform.quality.lineage import LineageTracker

        handler, records = self._capture()
        tracker = LineageTracker()
        tracker.record("p1", "person", "file.md", "TestPipeline")
        messages = [r.getMessage() for r in records]
        assert any("Lineage recorded" in m for m in messages)

    def test_pipeline_warning_on_transform_error(self, tmp_path):
        """Malformed markdown file triggers a WARNING-level log."""
        import textwrap

        from data_platform.etl.loaders import RepositoryLoader
        from data_platform.etl.markdown_loader import MarkdownETLPipeline
        from data_platform.knowledge_base.reader import KnowledgeBaseReader
        from data_platform.repositories.people import PeopleRepository

        (tmp_path / "people").mkdir()
        (tmp_path / "people" / "bad.md").write_text(
            textwrap.dedent("""\
                ---
                id: bad-001
                ---
                No name field here.
            """)
        )
        handler, records = self._capture()
        pipeline = MarkdownETLPipeline(
            reader=KnowledgeBaseReader(tmp_path),
            loader=RepositoryLoader(people_repo=PeopleRepository()),
        )
        pipeline.run()
        warnings = [r for r in records if r.levelno >= logging.WARNING]
        assert len(warnings) >= 1

    def test_json_logs_produce_valid_json_per_line(self):
        import io

        buf = io.StringIO()
        root = logging.getLogger(LOGGER_NAME)
        root.handlers.clear()
        root.setLevel(logging.DEBUG)
        handler = logging.StreamHandler(buf)
        handler.setFormatter(_JsonFormatter())
        root.addHandler(handler)

        from data_platform.quality.lineage import LineageTracker

        tracker = LineageTracker()
        tracker.record("c1", "company", "acme.md", "TestPipeline")
        handler.flush()

        output = buf.getvalue().strip()
        assert output, "Expected at least one log line"
        for line in output.splitlines():
            parsed = json.loads(line)
            assert "message" in parsed
