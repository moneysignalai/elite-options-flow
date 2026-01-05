import json
from datetime import datetime
from dateutil import parser

from src.engine.cluster import ClusterBuilder
from src.massive.models import OptionTrade, OptionSnapshot


def test_cluster_build():
    trades_data = json.load(open('tests/fixtures/sample_trades.json'))
    trades = [OptionTrade(**{**t, "trade_time": parser.parse(t["trade_time"])}) for t in trades_data]
    snapshot = OptionSnapshot(
        option_symbol="SPY240621C00450000",
        underlying="SPY",
        expiry=datetime(2024, 6, 21).date(),
        strike=450,
        call_put="C",
        oi=1000,
        iv=0.2,
        delta=0.5,
        gamma=0.1,
        underlying_price=445,
    )
    builder = ClusterBuilder(window_seconds=90)
    clusters = builder.build(trades, snapshot)
    assert len(clusters) == 1
    c = clusters[0]
    assert c.contracts_total == 150
    assert round(c.premium_total, 2) == 23000.0
    assert c.ask_side_ratio == 0
