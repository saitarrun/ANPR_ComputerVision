"""Structured JSON logging for audit trail and operational observability."""

import logging
import json
from datetime import datetime, timezone
from typing import Any, Optional, Dict
from contextlib import contextmanager
from contextvars import ContextVar

# Context variable to store request-scoped metadata
audit_context: ContextVar[Dict[str, Any]] = ContextVar(
    "audit_context", default={"timestamp": None, "request_id": None}
)


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add context from audit_context
        ctx = audit_context.get()
        if ctx:
            log_obj.update(ctx)

        # Add extra fields (user_id, action, resource, etc.)
        if hasattr(record, "user_id"):
            log_obj["user_id"] = record.user_id
        if hasattr(record, "action"):
            log_obj["action"] = record.action
        if hasattr(record, "resource"):
            log_obj["resource"] = record.resource
        if hasattr(record, "ip"):
            log_obj["ip"] = record.ip
        if hasattr(record, "status"):
            log_obj["status"] = record.status
        if hasattr(record, "region_id"):
            log_obj["region_id"] = record.region_id
        if hasattr(record, "query_type"):
            log_obj["query_type"] = record.query_type

        # Add exception info if present
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj)


def setup_audit_logging(level: str = "INFO") -> logging.Logger:
    """Configure structured logging for audit trail.

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("audit")
    logger.setLevel(getattr(logging, level))

    # Create handler
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter())

    logger.addHandler(handler)
    return logger


@contextmanager
def audit_log_context(
    request_id: str,
    user_id: Optional[str] = None,
    ip: Optional[str] = None,
) -> None:
    """Context manager to set audit logging context.

    Usage:
        with audit_log_context(request_id, user_id, ip):
            logger.info("data_access", extra={"region_id": "...", "query_type": "..."})
    """
    token = audit_context.set(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "user_id": user_id,
            "ip": ip,
        }
    )
    try:
        yield
    finally:
        audit_context.reset(token)


# Pre-configured logger for use in routers
audit_logger = setup_audit_logging()
