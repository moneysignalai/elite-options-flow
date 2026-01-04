import structlog
import logging
import sys


def configure_logging():
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.KeyValueRenderer(key_order=["event"]),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger():
    return structlog.get_logger()
