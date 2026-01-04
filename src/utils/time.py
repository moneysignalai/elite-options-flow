from datetime import datetime, time, timedelta
import pytz

def now_tz(tz_name: str = "America/New_York") -> datetime:
    return datetime.now(pytz.timezone(tz_name))


def within_window(current: datetime, start: str, end: str, enable_pre: bool, enable_after: bool) -> bool:
    start_hour, start_minute = map(int, start.split(":"))
    end_hour, end_minute = map(int, end.split(":"))
    start_time = time(start_hour, start_minute)
    end_time = time(end_hour, end_minute)
    if enable_pre and current.time() < start_time:
        return True
    if enable_after and current.time() > end_time:
        return True
    return start_time <= current.time() <= end_time


def dte(expiry, current=None):
    current = current or now_tz()
    if hasattr(expiry, 'date'):
        expiry_date = expiry.date()
    else:
        expiry_date = expiry
    return (expiry_date - current.date()).days


def sleep_seconds(outside: bool, interval: int) -> int:
    return interval if not outside else max(interval, interval * 2)
