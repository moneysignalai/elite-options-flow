import logging
import os
import sys
import uuid

import structlog


def _environment() -> str:
    return os.getenv("ENV", os.getenv("RENDER_ENV", os.getenv("ENVIRONMENT", "prod")))


def _git_sha() -> str:
    return os.getenv("GIT_SHA", os.getenv("RENDER_GIT_COMMIT", "unknown"))


def _run_id() -> str:
    return os.getenv("RUN_ID", uuid.uuid4().hex[:8])


def configure_logging(level: str = "INFO"):
    logging.basicConfig(stream=sys.stdout, level=getattr(logging, level.upper(), logging.INFO), format="%(message)s")
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level.upper(), logging.INFO)),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(service: str = "app", run_id: str | None = None):
    configure_logging()
    return structlog.get_logger().bind(
        service=service,
        env=_environment(),
        git_sha=_git_sha(),
        run_id=run_id or _run_id(),
    )
