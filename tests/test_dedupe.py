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
    manager = CooldownManager(cooldown_seconds=60 * 60)
    cluster = DummyCluster()
    suppress, reason, remaining, meta = manager.should_suppress(cluster, 5)
    assert suppress is False
    manager.mark_sent(cluster, 5)
    suppress, reason, remaining, meta = manager.should_suppress(cluster, 5)
    assert suppress is True
    assert remaining is not None


def test_cooldown_scope_contract_vs_other():
    manager = CooldownManager(cooldown_seconds=60 * 5, scope="contract")
    cluster_a = DummyCluster()
    cluster_b = DummyCluster()
    cluster_b.option_symbol = "TEST240630P00100000"
    manager.mark_sent(cluster_a, 6)
    suppress_a, _, _, _ = manager.should_suppress(cluster_a, 6)
    suppress_b, _, _, _ = manager.should_suppress(cluster_b, 6)
    assert suppress_a is True
    assert suppress_b is False


def test_cooldown_ignored_when_not_sent():
    manager = CooldownManager(cooldown_seconds=60 * 5, scope="contract")
    cluster = DummyCluster()
    suppress, _, _, _ = manager.should_suppress(cluster, 4)
    assert suppress is False
    suppress_again, _, _, _ = manager.should_suppress(cluster, 4)
    assert suppress_again is False
