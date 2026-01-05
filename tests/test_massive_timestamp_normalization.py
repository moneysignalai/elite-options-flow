from datetime import datetime, timezone

from src.massive.timestamp import normalize_timestamp_to_datetime


def test_normalize_nanoseconds_timestamp():
    ts = 1_767_643_805_366_820_625
    dt = normalize_timestamp_to_datetime(ts)

    assert dt is not None
    assert dt.year == 2026
    assert dt.tzinfo == timezone.utc


def test_normalize_milliseconds_timestamp():
    ts = 1_767_643_805_366
    dt = normalize_timestamp_to_datetime(ts)

    assert dt is not None
    assert dt.year == 2026


def test_normalize_seconds_timestamp():
    ts = 1_767_643_805
    dt = normalize_timestamp_to_datetime(ts)

    assert dt is not None
    assert dt.year == 2026
