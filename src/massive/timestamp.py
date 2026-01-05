from datetime import datetime, timezone
from typing import Any


def normalize_timestamp_to_datetime(ts: int | float | str | None) -> datetime | None:
    if ts is None:
        return None

    try:
        if isinstance(ts, str):
            ts = ts.strip()
            if ts == "":
                return None
            ts_int = int(float(ts))
        else:
            ts_int = int(ts)
    except Exception:  # noqa: BLE001
        return None

    try:
        if ts_int > 1_000_000_000_000_000:
            seconds = ts_int / 1_000_000_000
        elif ts_int > 1_000_000_000_000:
            seconds = ts_int / 1_000
        else:
            seconds = float(ts_int)
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except Exception:  # noqa: BLE001
        return None
