from datetime import datetime
from src.engine.dedupe import CooldownManager


class DummyCluster:
    def __init__(self):
        self.underlying = "TEST"
        self.expiry = datetime(2024, 6, 21)
        self.strike = 100
        self.call_put = "C"
        self.premium_total = 10000


def test_cooldown():
    manager = CooldownManager(cooldown_minutes=60)
    cluster = DummyCluster()
    suppress, reason, remaining = manager.should_suppress(cluster, 5)
    assert suppress is False
    suppress, reason, remaining = manager.should_suppress(cluster, 5)
    assert suppress is True
    assert remaining is not None
