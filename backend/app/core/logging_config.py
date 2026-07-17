"""Structured JSON logging configuration with trace_id support."""

import logging
import logging.config
from contextvars import ContextVar

# Request trace id propagated across log records and returned to callers.
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


class TraceIdFilter(logging.Filter):
    """Inject current trace_id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = trace_id_var.get()  # type: ignore[attr-defined]
        return True


LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s %(trace_id)s %(pathname)s %(lineno)d",
        },
    },
    "filters": {
        "trace_id": {
            "()": "app.core.logging_config.TraceIdFilter",
        },
    },
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "level": "INFO",
            "formatter": "json",
            "stream": "ext://sys.stdout",
            "filters": ["trace_id"],
        },
    },
    "root": {
        "level": "INFO",
        "handlers": ["stdout"],
    },
    "loggers": {
        "uvicorn": {"level": "INFO", "handlers": ["stdout"], "propagate": False},
        "uvicorn.access": {"level": "INFO", "handlers": ["stdout"], "propagate": False},
    },
}


def setup_logging(log_level: str = "INFO") -> None:
    """Apply structured JSON logging configuration."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    config = LOGGING_CONFIG.copy()
    config["root"]["level"] = level
    config["handlers"]["stdout"]["level"] = level
    for logger_name in config.get("loggers", {}):
        config["loggers"][logger_name]["level"] = level
    logging.config.dictConfig(config)
