"""
Central logging configuration for the data platform.

All modules obtain their logger via :func:`get_logger` which returns a child
of the ``data_platform`` hierarchy.  This lets callers silence or adjust the
entire platform with a single handler or level change.

Quick start::

    # Application / script entry-point
    from data_platform.log import configure_logging
    configure_logging(level="DEBUG")

    # --- or, configure via config.yaml ---
    from data_platform.config import get_config
    # configure_logging is called automatically when get_config() is invoked
    # if a `logging:` section is present in config.yaml.

Every module uses the module-level logger pattern::

    from data_platform.log import get_logger
    logger = get_logger(__name__)
    logger.info("something happened")

Log levels used across the codebase
--------------------------------------
* **DEBUG**   – fine-grained events: individual file reads, SQL queries, per-record transforms.
* **INFO**    – normal operational events: connector connect/disconnect, pipeline start/finish.
* **WARNING** – recoverable problems: transform errors, data quality violations.
* **ERROR**   – serious failures that may require human attention.
* **CRITICAL**– fatal errors that prevent the platform from operating.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

# Root logger name for the entire data platform hierarchy.
LOGGER_NAME = "data_platform"

# Fields that are part of every LogRecord and should not be surfaced as extras
# in the JSON formatter.
_LOG_RECORD_BUILTIN_ATTRS: frozenset[str] = frozenset(
    {
        "args",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "id",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


class _TextFormatter(logging.Formatter):
    """Human-readable multi-field log line.

    Format::

        2024-01-15T12:34:56+0000 [INFO    ] data_platform.etl.base – Pipeline started
    """

    DEFAULT_FMT = "%(asctime)s [%(levelname)-8s] %(name)s – %(message)s"
    DEFAULT_DATEFMT = "%Y-%m-%dT%H:%M:%S%z"

    def __init__(self) -> None:
        super().__init__(fmt=self.DEFAULT_FMT, datefmt=self.DEFAULT_DATEFMT)


class _JsonFormatter(logging.Formatter):
    """Emit each log record as a single-line JSON object.

    The output is suitable for log-aggregation pipelines (Datadog, Splunk,
    Cloud Logging, etc.).  Every record contains at minimum::

        {
          "timestamp": "2024-01-15T12:34:56.789+00:00",
          "level": "INFO",
          "logger": "data_platform.etl.base",
          "message": "Pipeline started"
        }

    Any keyword arguments passed via ``extra={"key": value}`` are merged into
    the top-level JSON object.
    """

    DEFAULT_DATEFMT = "%Y-%m-%dT%H:%M:%S%z"

    def __init__(self) -> None:
        super().__init__(datefmt=self.DEFAULT_DATEFMT)

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)

        # Merge any `extra={}` fields supplied by the caller.
        for key, val in record.__dict__.items():
            if key not in _LOG_RECORD_BUILTIN_ATTRS:
                payload[key] = val

        return json.dumps(payload, default=str)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_logger(name: str) -> logging.Logger:
    """Return a logger scoped to the ``data_platform`` hierarchy.

    Parameters
    ----------
    name:
        Typically ``__name__`` of the calling module.  If the name does not
        already start with ``"data_platform"``, the prefix is prepended
        automatically so all platform logs share the same root logger.

    Returns
    -------
    logging.Logger
        Logger whose effective name is ``data_platform.<name>`` (or just
        ``data_platform`` when *name* is already the root).
    """
    if name == LOGGER_NAME or name.startswith(f"{LOGGER_NAME}."):
        return logging.getLogger(name)
    return logging.getLogger(f"{LOGGER_NAME}.{name}")


def configure_logging(
    level: str = "INFO",
    json_logs: bool = False,
    log_file: str | None = None,
) -> None:
    """Configure the ``data_platform`` root logger.

    This is idempotent: calling it multiple times replaces the previous
    handler set (useful when re-configuring from a loaded config file).

    Parameters
    ----------
    level:
        Minimum log level to emit.  Accepts standard Python level names
        (``"DEBUG"``, ``"INFO"``, ``"WARNING"``, ``"ERROR"``, ``"CRITICAL"``).
        Defaults to ``"INFO"``.
    json_logs:
        When ``True``, format each record as a single-line JSON object.
        Ideal for log aggregation pipelines.  Defaults to ``False``.
    log_file:
        Optional path to a log file.  When set, records are written to both
        *stdout* **and** the file simultaneously.  Defaults to ``None``
        (stdout only).
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    root_logger = logging.getLogger(LOGGER_NAME)
    root_logger.setLevel(numeric_level)
    # Clear any previously installed handlers so reconfiguration is clean.
    root_logger.handlers.clear()
    # Do not propagate to the root stdlib logger to avoid duplicate output.
    root_logger.propagate = False

    formatter: logging.Formatter = _JsonFormatter() if json_logs else _TextFormatter()

    # Always emit to stdout.
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(numeric_level)
    sh.setFormatter(formatter)
    root_logger.addHandler(sh)

    # Optionally also write to a file.
    if log_file:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(numeric_level)
        fh.setFormatter(formatter)
        root_logger.addHandler(fh)
