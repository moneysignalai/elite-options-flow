from datetime import timedelta
from typing import Dict, List

from src.massive.models import OptionTrade, OptionQuote


class TradeQuoteMatcher:
    def __init__(self, window_seconds: int):
        self.window = timedelta(seconds=window_seconds)

    def label_aggression(self, trades: List[OptionTrade], quotes: List[OptionQuote]) -> List[OptionTrade]:
        quotes_by_symbol = sorted(quotes, key=lambda q: q.quote_time)
        labeled = []
        for trade in trades:
            quote = self._nearest_quote(trade, quotes_by_symbol)
            side = self._infer_side(trade, quote) if quote else None
            trade_payload: Dict = trade.dict()
            trade_payload["side"] = side or trade_payload.get("side")
            labeled.append(OptionTrade(**trade_payload))
        return labeled

    def _nearest_quote(self, trade: OptionTrade, quotes: List[OptionQuote]):
        candidates = [q for q in quotes if abs((trade.trade_time - q.quote_time).total_seconds()) <= self.window.total_seconds()]
        if not candidates:
            return None
        candidates.sort(key=lambda q: abs((trade.trade_time - q.quote_time).total_seconds()))
        return candidates[0]

    @staticmethod
    def _infer_side(trade: OptionTrade, quote: OptionQuote | None) -> str | None:
        if not quote:
            return None
        if trade.price >= quote.ask:
            return "ASK_SIDE"
        if trade.price <= quote.bid:
            return "BID_SIDE"
        return "MID"
