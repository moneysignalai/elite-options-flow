from datetime import datetime, timedelta
from typing import List
from pydantic import BaseModel

from src.massive.models import OptionTrade, OptionSnapshot
from src.utils.time import dte


class FlowCluster(BaseModel):
    option_symbol: str
    underlying: str
    expiry: datetime
    strike: float
    call_put: str
    trades: List[OptionTrade]
    premium_total: float
    contracts_total: float
    prints_count: int
    duration_sec: float
    avg_fill_price: float
    ask_side_ratio: float
    sweep_score: float
    oi: float | None
    dte: int
    otm_pct: float | None


class ClusterBuilder:
    def __init__(self, window_seconds: int):
        self.window = timedelta(seconds=window_seconds)

    def build(self, trades: List[OptionTrade], snapshot: OptionSnapshot) -> List[FlowCluster]:
        trades = sorted(trades, key=lambda t: t.trade_time)
        clusters: List[FlowCluster] = []
        bucket: List[OptionTrade] = []
        for trade in trades:
            if not bucket:
                bucket.append(trade)
                continue
            if trade.trade_time - bucket[0].trade_time <= self.window:
                bucket.append(trade)
            else:
                clusters.append(self._finalize(bucket, snapshot))
                bucket = [trade]
        if bucket:
            clusters.append(self._finalize(bucket, snapshot))
        return clusters

    def _finalize(self, trades: List[OptionTrade], snapshot: OptionSnapshot) -> FlowCluster:
        premium_total = sum(t.price * t.size * 100 for t in trades)
        contracts_total = sum(t.size for t in trades)
        duration = (trades[-1].trade_time - trades[0].trade_time).total_seconds() or 1
        ask_ratio = sum(1 for t in trades if t.side == "ASK_SIDE") / len(trades)
        avg_price = sum(t.price for t in trades) / len(trades)
        sweep_score = min(1.0, len(trades) / max(duration, 1))
        otm_pct = None
        if snapshot and snapshot.underlying_price:
            direction = 1 if snapshot.call_put.upper() == "C" else -1
            intrinsic = (snapshot.underlying_price - snapshot.strike * direction)
            otm_pct = max(0.0, snapshot.strike - snapshot.underlying_price) / snapshot.underlying_price * 100 if snapshot.call_put.upper() == "P" else max(0.0, snapshot.underlying_price - snapshot.strike) / snapshot.underlying_price * 100
        return FlowCluster(
            option_symbol=snapshot.option_symbol,
            underlying=snapshot.underlying,
            expiry=datetime.combine(snapshot.expiry, datetime.min.time()),
            strike=snapshot.strike,
            call_put=snapshot.call_put,
            trades=trades,
            premium_total=premium_total,
            contracts_total=contracts_total,
            prints_count=len(trades),
            duration_sec=duration,
            avg_fill_price=avg_price,
            ask_side_ratio=ask_ratio,
            sweep_score=sweep_score,
            oi=snapshot.oi,
            dte=dte(snapshot.expiry),
            otm_pct=otm_pct,
        )
