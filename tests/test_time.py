from datetime import datetime
from zoneinfo import ZoneInfo

from src.utils.time import within_window


def test_within_window_rth_open():
    current = datetime(2024, 1, 2, 10, 48, tzinfo=ZoneInfo("America/New_York"))

    is_open, reason = within_window(
        current, start="09:30", end="16:00", enable_pre=False, enable_after=False
    )

    assert is_open is True
    assert reason == "regular_hours"
