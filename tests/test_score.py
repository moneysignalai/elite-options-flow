from datetime import datetime

from src.engine.score import score_cluster
from src.engine.cluster import FlowCluster


def _cluster():
    return FlowCluster(
        option_symbol="TEST",
        underlying="TEST",
        expiry=datetime(2024, 6, 21),
        strike=100,
        call_put="C",
        trades=[],
        premium_total=300000,
        contracts_total=500,
        prints_count=10,
        duration_sec=60,
        avg_fill_price=1.5,
        ask_side_ratio=0.8,
        sweep_score=0.6,
        oi=200,
        dte=2,
        otm_pct=6,
    )


def test_score_components():
    score, components, tags = score_cluster(_cluster())
    assert score <= 10
    assert components["size"] > 0
    assert "aggressive" in tags
