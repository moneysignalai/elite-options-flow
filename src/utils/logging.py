import contextvars
import logging
import os
import sys
import structlog
from typing import Any, Callable, Optional


_request_id_ctx = contextvars.ContextVar("request_id", default=None)
_run_id_ctx = contextvars.ContextVar("run_id", default=None)
_alert_id_ctx = contextvars.ContextVar("alert_id", default=None)
_configured = False


def _environment() -> str:
    return os.getenv("ENVIRONMENT", "prod")


def _git_sha() -> str:
    return os.getenv("GIT_SHA", "unknown")


def _log_level() -> int:
    name = os.getenv("LOG_LEVEL", "INFO").upper()
    return getattr(logging, name, logging.INFO)


def _add_contextvars(_: structlog.types.WrappedLogger, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    run_id = _run_id_ctx.get()
    request_id = _request_id_ctx.get()
    alert_id = _alert_id_ctx.get()
    if run_id:
        event_dict.setdefault("run_id", run_id)
    if request_id:
        event_dict.setdefault("request_id", request_id)
    if alert_id:
        event_dict.setdefault("alert_id", alert_id)
    return event_dict


def _add_base_fields(logger: structlog.types.WrappedLogger, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    context = getattr(logger, "_context", {}) or {}
    event_dict.setdefault("service", context.get("service", "app"))
    event_dict.setdefault("env", _environment())
    event_dict.setdefault("git_sha", _git_sha())
    return event_dict


def configure_logging() -> None:
    global _configured
    if _configured:
        return

    logging.basicConfig(stream=sys.stdout, level=_log_level(), format="%(message)s")
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.add_log_level,
            _add_contextvars,
            _add_base_fields,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(_log_level()),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(service_name: str) -> structlog.stdlib.BoundLogger:
    configure_logging()
    return structlog.get_logger().bind(service=service_name, env=_environment(), git_sha=_git_sha())


def set_request_id(request_id: Optional[str]) -> None:
    if request_id is None:
        _request_id_ctx.set(None)
    else:
        _request_id_ctx.set(request_id)


def set_run_id(run_id: Optional[str]) -> None:
    if run_id is None:
        _run_id_ctx.set(None)
    else:
        _run_id_ctx.set(run_id)


def set_alert_id(alert_id: Optional[str]) -> None:
    if alert_id is None:
        _alert_id_ctx.set(None)
    else:
        _alert_id_ctx.set(alert_id)


def log_event(logger: structlog.stdlib.BoundLogger, event_name: str, **fields: Any) -> None:
    """Log a structured info event with the given name and fields."""

    logger.info(event_name, **fields)


def log_error(log: structlog.stdlib.BoundLogger, where: str, error: Exception) -> None:
    log.exception(
        "error",
        where=where,
        exception_type=type(error).__name__,
        exception_message=str(error),
    )


def with_log_context(**kwargs: Any) -> Callable[[structlog.stdlib.BoundLogger], structlog.stdlib.BoundLogger]:
    def binder(log: structlog.stdlib.BoundLogger) -> structlog.stdlib.BoundLogger:
        return log.bind(**{k: v for k, v in kwargs.items() if v is not None})

    return binder
