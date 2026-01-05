from datetime import date, datetime
from types import SimpleNamespace

from src.engine.alert_router import AlertRouter
from src.engine.cluster import ClusterBuilder
from src.engine.dedupe import CooldownManager
from src.engine.ingest import TradeQuoteMatcher
from src.massive.models import OptionQuote, OptionSnapshot, OptionTrade
from src.worker import run_once


class StubMessenger:
    def __init__(self):
        self.sent = []

    def send(self, payload):
        self.sent.append(payload)


class StubRepo:
    def save_alert(self, cluster, setup, score, components, tags, template):
        return "alert-1"


class StubDiscovery:
    def __init__(self, contracts):
        self.contracts = contracts

    def contracts_for(self, _):
        return self.contracts


class StubClient:
    def __init__(self, snapshot, trades=None, quotes=None):
        self.snapshot = snapshot
        self.trades = trades or []
        self.quotes = quotes or []

    def get_contract_snapshot(self, *_args, **_kwargs):
        return self.snapshot

    def get_option_trades(self, *_args, **_kwargs):
        return self.trades

    def get_option_quotes(self, *_args, **_kwargs):
        return self.quotes


class ConfigFactory:
    @staticmethod
    def build(alert_threshold: float = 0.0):
        scan = SimpleNamespace(
            chain_discovery="static",
            aggression_window_seconds=120,
            cluster_window_seconds=90,
            max_lookback_minutes=5,
            gamma_dte_max=3,
            structural_dte_min=30,
            alert_score_threshold=alert_threshold,
            deep_dive_threshold=9.0,
            medium_threshold=7.0,
            cooldown_minutes=0,
            tickers=["TEST"],
        )
        telegram = SimpleNamespace(bot_token=None, chat_id=None)
        massive = SimpleNamespace()
        return SimpleNamespace(scan=scan, telegram=telegram, massive=massive, database_url=None)


class StubLogger:
    def info(self, *_args, **_kwargs):
        return None

    def bind(self, **_kwargs):
        return self


class NoCooldown(CooldownManager):
    def __init__(self):
        super().__init__(0)

    def should_suppress(self, cluster, score: float):
        return False, "", None



def _router(config):
    messenger = StubMessenger()
    repo = StubRepo()
    cooldown = NoCooldown()
    return AlertRouter(repo, messenger, cooldown, config, logger=StubLogger()), messenger


def test_trades_mode_generates_alert():
    snapshot = OptionSnapshot(
        option_symbol="TEST240621C00100000",
        underlying="TEST",
        expiry=date.today(),
        strike=100.0,
        call_put="C",
        oi=1000,
        iv=0.5,
        delta=0.5,
        gamma=0.1,
        underlying_price=105.0,
        day_volume=500,
    )
    trades = [
        OptionTrade(
            option_symbol=snapshot.option_symbol,
            underlying="TEST",
            trade_time=datetime.utcnow(),
            price=5.0,
            size=200,
            side="ASK_SIDE",
        )
    ]
    quotes = [
        OptionQuote(
            option_symbol=snapshot.option_symbol,
            bid=4.9,
            ask=5.1,
            quote_time=datetime.utcnow(),
        )
    ]
    client = StubClient(snapshot, trades=trades, quotes=quotes)
    discovery = StubDiscovery([snapshot.option_symbol])
    config = ConfigFactory.build(alert_threshold=0.0)
    matcher = TradeQuoteMatcher(config.scan.aggression_window_seconds)
    cluster_builder = ClusterBuilder(config.scan.cluster_window_seconds)
    router, messenger = _router(config)

    result = run_once("TEST", client, discovery, matcher, cluster_builder, router, config, StubLogger())

    assert result["sent"] == 1
    assert messenger.sent[0]["mode"] == "trades"
    assert messenger.sent[0]["score"] > 0


def test_snapshot_fallback_uses_volume():
    snapshot = OptionSnapshot(
        option_symbol="TEST240621C00100000",
        underlying="TEST",
        expiry=date.today(),
        strike=100.0,
        call_put="P",
        oi=500,
        iv=0.5,
        delta=0.5,
        gamma=0.1,
        underlying_price=95.0,
        day_volume=250,
        last_quote=OptionQuote(
            option_symbol="TEST240621C00100000",
            bid=2.0,
            ask=2.2,
            quote_time=datetime.utcnow(),
        ),
    )
    client = StubClient(snapshot, trades=[], quotes=[])
    discovery = StubDiscovery([snapshot.option_symbol])
    config = ConfigFactory.build(alert_threshold=0.0)
    matcher = TradeQuoteMatcher(config.scan.aggression_window_seconds)
    cluster_builder = ClusterBuilder(config.scan.cluster_window_seconds)
    router, messenger = _router(config)

    result = run_once("TEST", client, discovery, matcher, cluster_builder, router, config, StubLogger())

    assert result["sent"] == 1
    assert messenger.sent[0]["mode"] == "snapshot"
    assert messenger.sent[0]["score"] > 0


def test_quotes_fallback_without_trades():
    snapshot = OptionSnapshot(
        option_symbol="TEST240621C00100000",
        underlying="TEST",
        expiry=date.today(),
        strike=100.0,
        call_put="C",
        oi=None,
        iv=0.5,
        delta=0.5,
        gamma=0.1,
        underlying_price=101.0,
        day_volume=None,
    )
    quotes = [
        OptionQuote(
            option_symbol=snapshot.option_symbol,
            bid=1.0,
            ask=1.2,
            quote_time=datetime.utcnow(),
        )
    ]
    client = StubClient(snapshot, trades=[], quotes=quotes)
    discovery = StubDiscovery([snapshot.option_symbol])
    config = ConfigFactory.build(alert_threshold=0.0)
    matcher = TradeQuoteMatcher(config.scan.aggression_window_seconds)
    cluster_builder = ClusterBuilder(config.scan.cluster_window_seconds)
    router, messenger = _router(config)

    result = run_once("TEST", client, discovery, matcher, cluster_builder, router, config, StubLogger())

    assert result["sent"] == 1
    assert messenger.sent[0]["mode"] == "quotes"
    assert messenger.sent[0]["score"] > 0


def test_empty_inputs_produce_no_clusters():
    snapshot = OptionSnapshot(
        option_symbol="TEST240621C00100000",
        underlying="TEST",
        expiry=date.today(),
        strike=100.0,
        call_put="C",
        oi=None,
        iv=None,
        delta=None,
        gamma=None,
        underlying_price=100.0,
    )
    client = StubClient(snapshot, trades=[], quotes=[])
    discovery = StubDiscovery([snapshot.option_symbol])
    config = ConfigFactory.build(alert_threshold=0.0)
    matcher = TradeQuoteMatcher(config.scan.aggression_window_seconds)
    cluster_builder = ClusterBuilder(config.scan.cluster_window_seconds)
    router, messenger = _router(config)

    result = run_once("TEST", client, discovery, matcher, cluster_builder, router, config, StubLogger())

    assert result["sent"] == 0
    assert messenger.sent == []
