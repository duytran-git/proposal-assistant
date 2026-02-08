"""Structured logging utilities for Proposal Assistant.

Provides structured logging with contextual fields:
- timestamp: ISO format timestamp
- thread_ts: Slack thread timestamp for correlation
- state: Current workflow state
- duration: Operation duration in milliseconds
"""

import json
import logging
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

# Log file path (project_root/logs/)
LOG_DIR = Path(__file__).parent.parent.parent.parent / "logs"
LOG_FILE = LOG_DIR / "proposal_assistant.log"


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured log output."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON with structured fields."""
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add structured context fields if present
        if hasattr(record, "thread_ts") and record.thread_ts:
            log_entry["thread_ts"] = record.thread_ts
        if hasattr(record, "state") and record.state:
            log_entry["state"] = record.state
        if hasattr(record, "duration_ms") and record.duration_ms is not None:
            log_entry["duration_ms"] = record.duration_ms
        if hasattr(record, "channel_id") and record.channel_id:
            log_entry["channel_id"] = record.channel_id
        if hasattr(record, "user_id") and record.user_id:
            log_entry["user_id"] = record.user_id
        if hasattr(record, "event") and record.event:
            log_entry["event"] = record.event
        if hasattr(record, "error_type") and record.error_type:
            log_entry["error_type"] = record.error_type

        # Add extra fields
        if hasattr(record, "extra_fields") and record.extra_fields:
            log_entry.update(record.extra_fields)

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


class StructuredLogger:
    """Logger wrapper that adds structured context to log messages."""

    def __init__(self, name: str):
        """Initialize structured logger.

        Args:
            name: Logger name (typically __name__).
        """
        self._logger = logging.getLogger(name)
        self._context: dict[str, Any] = {}

    def bind(self, **kwargs: Any) -> "StructuredLogger":
        """Create a new logger with additional bound context.

        Args:
            **kwargs: Context fields to bind (thread_ts, state, etc.).

        Returns:
            New StructuredLogger instance with merged context.
        """
        new_logger = StructuredLogger(self._logger.name)
        new_logger._context = {**self._context, **kwargs}
        return new_logger

    def _log(
        self,
        level: int,
        msg: str,
        *args: Any,
        exc_info: bool = False,
        **kwargs: Any,
    ) -> None:
        """Internal log method that adds context fields."""
        # Merge bound context with call-time kwargs
        extra = {**self._context, **kwargs}

        # Create log record with extra fields
        record_kwargs: dict[str, Any] = {}
        for key in ["thread_ts", "state", "duration_ms", "channel_id", "user_id", "event", "error_type"]:
            if key in extra:
                record_kwargs[key] = extra.pop(key)

        # Remaining kwargs go into extra_fields
        if extra:
            record_kwargs["extra_fields"] = extra

        self._logger.log(level, msg, *args, exc_info=exc_info, extra=record_kwargs)

    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log debug message with structured context."""
        self._log(logging.DEBUG, msg, *args, **kwargs)

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log info message with structured context."""
        self._log(logging.INFO, msg, *args, **kwargs)

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log warning message with structured context."""
        self._log(logging.WARNING, msg, *args, **kwargs)

    def error(self, msg: str, *args: Any, exc_info: bool = False, **kwargs: Any) -> None:
        """Log error message with structured context."""
        self._log(logging.ERROR, msg, *args, exc_info=exc_info, **kwargs)

    def exception(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log exception with traceback and structured context."""
        self._log(logging.ERROR, msg, *args, exc_info=True, **kwargs)

    @contextmanager
    def timed(self, operation: str, **kwargs: Any) -> Generator[None, None, None]:
        """Context manager that logs operation duration.

        Args:
            operation: Name of the operation being timed.
            **kwargs: Additional context fields.

        Yields:
            None

        Example:
            with logger.timed("llm_generation", thread_ts="123"):
                result = llm.generate(...)
        """
        start = time.perf_counter()
        try:
            yield
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            self.info(
                f"{operation} completed",
                duration_ms=duration_ms,
                operation=operation,
                **kwargs,
            )


def setup_logging(log_level: str = "INFO") -> None:
    """Configure logging with file and console handlers.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    # Ensure log directory exists
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Get root logger for proposal_assistant
    root_logger = logging.getLogger("proposal_assistant")
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # File handler with structured JSON format
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)  # Log everything to file
    file_handler.setFormatter(StructuredFormatter())
    root_logger.addHandler(file_handler)

    # Console handler with human-readable format
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    console_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # Prevent propagation to root logger
    root_logger.propagate = False


def get_logger(name: str) -> StructuredLogger:
    """Get a structured logger for the given name.

    Args:
        name: Logger name (typically __name__).

    Returns:
        StructuredLogger instance.

    Example:
        logger = get_logger(__name__)
        logger.info("Processing request", thread_ts="123", state="GENERATING")

        # With bound context
        ctx_logger = logger.bind(thread_ts="123", channel_id="C456")
        ctx_logger.info("Step 1 complete")
        ctx_logger.info("Step 2 complete")

        # With timing
        with logger.timed("llm_call", thread_ts="123"):
            result = expensive_operation()
    """
    return StructuredLogger(name)
