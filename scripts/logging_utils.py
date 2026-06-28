#!/usr/bin/env python3
"""Shared logging utilities for WineBot operational scripts.

Usage:
    from logging_utils import log_start, log_complete, log_error, StructuredLogger

    logger = StructuredLogger("my-script")
    logger.start("Processing widgets")
    # ... do work ...
    logger.complete(f"Processed {n} widgets")
    logger.error("Failed to process widget", exc_info=True)

JSON output format:
    {"ts": "2026-06-28T12:34:56Z", "level": "info", "logger": "my-script",
     "message": "...", "elapsed_s": 123.4, "details": {...}}
"""
import json
import os
import sys
import time
import traceback
from datetime import UTC, datetime
from typing import Any


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json(entry: dict):
    """Write a JSON log line to stderr (so it doesn't interfere with stdout data)."""
    print(json.dumps(entry, default=str), file=sys.stderr, flush=True)


class StructuredLogger:
    """Structured JSON logger for operational scripts.

    Writes JSON lines to stderr. Each line has ts, level, logger, message.
    """

    def __init__(self, name: str):
        self.name = name
        self._start_time: float | None = None
        self._step_times: dict[str, float] = {}

    def _log(self, level: str, message: str, **kwargs):
        entry = {
            "ts": _timestamp(),
            "level": level,
            "logger": self.name,
            "message": message,
        }
        if self._start_time is not None:
            entry["elapsed_s"] = round(time.time() - self._start_time, 2)
        if kwargs:
            entry["details"] = {k: v for k, v in kwargs.items() if v is not None}
        _write_json(entry)

    def start(self, message: str, **kwargs):
        """Log script/operation start."""
        self._start_time = time.time()
        self._log("info", message, **kwargs)

    def step(self, name: str, message: str, **kwargs):
        """Log a step within an operation."""
        self._step_times[name] = time.time()
        self._log("info", f"[{name}] {message}", **kwargs)

    def complete(self, message: str, **kwargs):
        """Log successful completion."""
        self._log("info", message, **kwargs)

    def warn(self, message: str, **kwargs):
        """Log a warning."""
        self._log("warn", message, **kwargs)

    def error(self, message: str, exc_info: bool = False, **kwargs):
        """Log an error. If exc_info=True, includes traceback."""
        if exc_info:
            kwargs["traceback"] = traceback.format_exc().strip().split("\n")
        self._log("error", message, **kwargs)

    def result(self, metric: str, value: Any, **kwargs):
        """Log a result metric."""
        self._log("result", f"{metric}={value}", metric=metric, value=value, **kwargs)


# ── Convenience functions for simple scripts ───────────────────────────────

_loggers: dict[str, StructuredLogger] = {}


def get_logger(name: str) -> StructuredLogger:
    """Get or create a named logger."""
    if name not in _loggers:
        _loggers[name] = StructuredLogger(name)
    return _loggers[name]


def log_start(message: str, **kwargs):
    """Quick-start a logger for the calling script's __name__."""
    import __main__
    name = os.path.splitext(os.path.basename(getattr(__main__, "__file__", "script")))[0]
    logger = get_logger(name)
    logger.start(message, **kwargs)
    return logger


def log_complete(logger: StructuredLogger, message: str, **kwargs):
    """Log completion from a logger returned by log_start."""
    logger.complete(message, **kwargs)


def log_error(logger: StructuredLogger, message: str, exc_info: bool = True, **kwargs):
    """Log an error from a logger returned by log_start."""
    logger.error(message, exc_info=exc_info, **kwargs)
