import time
from functools import wraps

from src.utils.logging import get_logger


def with_retries(retries: int = 2, backoff: float = 1.5):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 0
            log = getattr(args[0], "logger", get_logger("app")) if args else get_logger("app")
            while True:
                try:
                    return func(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001
                    attempt += 1
                    if attempt > retries:
                        log.exception(
                            "operation failed",
                            event="error",
                            where=func.__name__,
                            exception_type=type(exc).__name__,
                            exception_message=str(exc),
                        )
                        raise
                    sleep_for = backoff ** attempt
                    log.warning(
                        "retrying",
                        event="retrying",
                        attempt=attempt,
                        sleep=sleep_for,
                        func=func.__name__,
                    )
                    time.sleep(sleep_for)
        return wrapper
    return decorator
