import time
from functools import wraps
from loguru import logger


def with_retries(retries: int = 2, backoff: float = 1.5):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001
                    attempt += 1
                    if attempt > retries:
                        logger.exception("operation failed", error=str(exc), func=func.__name__)
                        raise
                    sleep_for = backoff ** attempt
                    logger.warning("retrying", attempt=attempt, sleep=sleep_for, func=func.__name__)
                    time.sleep(sleep_for)
        return wrapper
    return decorator
