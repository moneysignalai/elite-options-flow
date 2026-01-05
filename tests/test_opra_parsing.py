from datetime import datetime, timezone

from src.massive.models import OptionSnapshot
from src.massive.opra import parse_opra_symbol


class DummyLogger:
    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def info(self, **kwargs):
        event = kwargs.pop("event", "")
        self.events.append((event, kwargs))


def test_parse_opra_symbol_calls_and_puts():
    nvda = parse_opra_symbol("O:NVDA260109C00050000")
    assert nvda is not None
    assert nvda["expiry"].isoformat() == "2026-01-09"
    assert nvda["strike"] == 50.0
    assert nvda["call_put"] == "C"
    assert nvda["root"] == "NVDA"

    tsla = parse_opra_symbol("O:TSLA260109P00150000")
    assert tsla is not None
    assert tsla["expiry"].isoformat() == "2026-01-09"
    assert tsla["strike"] == 150.0
    assert tsla["call_put"] == "P"
    assert tsla["root"] == "TSLA"


def test_parse_opra_symbol_invalid_returns_none():
    assert parse_opra_symbol("INVALID") is None
    assert parse_opra_symbol("O:SPY990231C00000000") is None


def test_snapshot_builds_from_symbol_when_fields_missing():
    logger = DummyLogger()
    payload = {
        "option_symbol": "O:NVDA260109C00050000",
        "underlying": "NVDA",
        "call_put": None,
        "last_quote": {
            "bid": 1.0,
            "ask": 2.0,
            "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc),
        },
    }

    snapshot = OptionSnapshot.from_snapshot_payload(payload, logger=logger)
    assert snapshot is not None
    assert snapshot.expiry.isoformat() == "2026-01-09"
    assert snapshot.strike == 50.0
    assert snapshot.call_put == "C"
    assert logger.events == []


def test_snapshot_missing_fields_logs_and_skips():
    logger = DummyLogger()
    payload = {
        "option_symbol": "BAD",
        "underlying": "BAD",
    }

    snapshot = OptionSnapshot.from_snapshot_payload(payload, logger=logger)

    assert snapshot is None
    assert ("opra_parse_failed", {"option_symbol": "BAD"}) in logger.events
    assert any(event[0] == "massive_quote_missing_fields" for event in logger.events)
