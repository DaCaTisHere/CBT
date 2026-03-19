"""
Logging configuration using structlog for structured logging
"""

import logging
import sys
from pathlib import Path
from typing import Optional

import structlog
from structlog.typing import FilteringBoundLogger

from src.core.config import settings


_dashboard_buffer = None

def set_dashboard_buffer(buf):
    global _dashboard_buffer
    _dashboard_buffer = buf

def _dashboard_bridge(logger, method_name, event_dict):
    """Structlog processor that copies log entries to the dashboard ring buffer."""
    if _dashboard_buffer is not None:
        from datetime import datetime, timezone
        _dashboard_buffer.append({
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "level": event_dict.get("level", method_name).upper(),
            "name": event_dict.get("logger", ""),
            "msg": event_dict.get("event", ""),
        })
    return event_dict

def setup_logging():
    """
    Setup structured logging with structlog
    """
    # Create logs directory if it doesn't exist
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Configure standard logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.LOG_LEVEL.value),
    )
    
    # Configure structlog with dashboard buffer bridge
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _dashboard_bridge,
            structlog.dev.ConsoleRenderer() if settings.ENVIRONMENT.value == "development"
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.LOG_LEVEL.value)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )


def get_logger(name: Optional[str] = None) -> FilteringBoundLogger:
    """
    Get a structured logger instance
    
    Args:
        name: Logger name (usually __name__)
    
    Returns:
        Structured logger
    """
    return structlog.get_logger(name)


# Setup logging on module import
setup_logging()

