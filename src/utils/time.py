from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo


def now_tz(tz_name: str = "America/New_York") -> datetime:
    return datetime.now(ZoneInfo(tz_name))


def within_window(
    current: datetime, start: str, end: str, enable_pre: bool, enable_after: bool
) -> tuple[bool, str, datetime, int]:
    market_tz = ZoneInfo("America/New_York")
    current_local = (
        current.astimezone(market_tz)
        if current.tzinfo is not None
        else current.replace(tzinfo=market_tz)
    )

    start_hour, start_minute = map(int, start.split(":"))
    end_hour, end_minute = map(int, end.split(":"))
    start_dt = datetime.combine(
        current_local.date(), time(start_hour, start_minute), tzinfo=market_tz
    )
    end_dt = datetime.combine(
        current_local.date(), time(end_hour, end_minute), tzinfo=market_tz
    )

    if current_local < start_dt:
        is_open = enable_pre
        reason = "pre_market" if enable_pre else "premarket_disabled"
        next_transition = start_dt
    elif current_local > end_dt:
        is_open = enable_after
        reason = "after_hours" if enable_after else "afterhours_disabled"
        next_transition = datetime.combine(
            current_local.date(), time(start_hour, start_minute), tzinfo=market_tz
        ) + timedelta(days=1)
    else:
        is_open = True
        reason = "regular_hours"
        next_transition = end_dt

    seconds_until_transition = max(
        0, int((next_transition - current_local).total_seconds())
    )
    return is_open, reason, next_transition, seconds_until_transition


def dte(expiry, current=None):
    current = current or now_tz()
    if hasattr(expiry, 'date'):
        expiry_date = expiry.date()
    else:
        expiry_date = expiry
    return (expiry_date - current.date()).days


def sleep_seconds(outside: bool, interval: int) -> int:
    return interval if not outside else max(interval, interval * 2)
