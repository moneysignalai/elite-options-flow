import contextvars
import logging
import os
import sys
import uuid
from typing import Any, Callable, Optional

import structlog


_request_id_ctx = contextvars.ContextVar("request_id", default=None)
_run_id_ctx = contextvars.ContextVar("run_id", default=None)
_alert_id_ctx = contextvars.ContextVar("alert_id", default=None)
_configured = False
_boot_run_id = uuid.uuid4().hex[:8]


def _environment() -> str:
    return os.getenv("ENV", os.getenv("RENDER_ENV", os.getenv("ENVIRONMENT", "prod")))


def _git_sha() -> str:
    return os.getenv("GIT_SHA", os.getenv("RENDER_GIT_COMMIT", "unknown"))


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
    event_dict.setdefault("run_id", _run_id_ctx.get() or _boot_run_id)
    return event_dict


def configure_logging() -> None:
    global _configured
    if _configured:
        return

    logging.basicConfig(stream=sys.stdout, level=_log_level(), format="%(message)s")
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
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
    return structlog.get_logger().bind(service=service_name)


def set_request_id(request_id: Optional[str]) -> None:
    _request_id_ctx.set(request_id)


def set_run_id(run_id: Optional[str]) -> None:
    _run_id_ctx.set(run_id)


def set_alert_id(alert_id: Optional[str]) -> None:
    _alert_id_ctx.set(alert_id)


def log_event(logger: structlog.stdlib.BoundLogger, event_name: str, **fields: Any) -> None:
    """Log a structured info event with the given name and fields."""

    logger.info(event=event_name, **fields)


def log_error(log: structlog.stdlib.BoundLogger, where: str, error: Exception) -> None:
    log.exception(
        event="error",
        where=where,
        exception_type=type(error).__name__,
        exception_message=str(error),
    )


def with_log_context(**kwargs: Any) -> Callable[[structlog.stdlib.BoundLogger], structlog.stdlib.BoundLogger]:
    def binder(log: structlog.stdlib.BoundLogger) -> structlog.stdlib.BoundLogger:
        return log.bind(**{k: v for k, v in kwargs.items() if v is not None})

    return binder


def _redact_params(params: dict[str, Any] | None) -> dict[str, Any] | None:
    if not params:
        return None
    redacted_keys = {"api_key", "apikey", "api-key", "authorization", "token"}
    sanitized: dict[str, Any] = {}
    for key, value in params.items():
        if key.lower() in redacted_keys:
            sanitized[key] = "***"
        else:
            sanitized[key] = value
    return sanitized


def log_massive_request(
    logger: structlog.stdlib.BoundLogger,
    method: str,
    url: str,
    params: dict[str, Any] | None = None,
    ticker: str | None = None,
    option_contract: str | None = None,
) -> None:
    log_event(
        logger,
        "massive_request",
        method=method,
        url=url,
        params=_redact_params(params),
        ticker=ticker,
        option_contract=option_contract,
    )


def log_massive_response(
    logger: structlog.stdlib.BoundLogger,
    status_code: int | None,
    elapsed_ms: float | None,
    content_type: str | None,
    top_level_keys: list[str] | None = None,
    parsed_count: int | None = None,
) -> None:
    log_event(
        logger,
        "massive_response",
        status_code=status_code,
        elapsed_ms=elapsed_ms,
        content_type=content_type,
        top_level_keys=top_level_keys,
        parsed_count=parsed_count,
    )


def log_massive_failure(
    logger: structlog.stdlib.BoundLogger,
    url: str,
    params: dict[str, Any] | None,
    exc: Exception,
    ticker: str | None = None,
    option_contract: str | None = None,
    status_code: int | None = None,
) -> None:
    log_event(
        logger,
        "massive_error",
        url=url,
        params=_redact_params(params),
        ticker=ticker,
        option_contract=option_contract,
        status_code=status_code,
        exception_type=type(exc).__name__,
        exception_message=str(exc),
    )
