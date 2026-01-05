from datetime import datetime, time
from zoneinfo import ZoneInfo


def now_tz(tz_name: str = "America/New_York") -> datetime:
    return datetime.now(ZoneInfo(tz_name))


def within_window(
    current: datetime, start: str, end: str, enable_pre: bool, enable_after: bool
) -> tuple[bool, str]:
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
        if enable_pre:
            return True, "pre_market"
        return False, "premarket_disabled"

    if current_local > end_dt:
        if enable_after:
            return True, "after_hours"
        return False, "afterhours_disabled"

    return True, "regular_hours"


def dte(expiry, current=None):
    current = current or now_tz()
    if hasattr(expiry, 'date'):
        expiry_date = expiry.date()
    else:
        expiry_date = expiry
    return (expiry_date - current.date()).days


def sleep_seconds(outside: bool, interval: int) -> int:
    return interval if not outside else max(interval, interval * 2)
