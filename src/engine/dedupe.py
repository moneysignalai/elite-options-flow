from datetime import datetime, timedelta
from typing import Dict


def cluster_key(cluster, scope: str = "contract") -> str:
    normalized_scope = (scope or "contract").lower()
    # Ticker scope is too coarse; fall back to a contract-level identifier
    if normalized_scope == "ticker":
        normalized_scope = "contract"
    if normalized_scope == "strategy":
        return f"{cluster.underlying}-{cluster.expiry.date()}-{cluster.strike}-{cluster.call_put}"
    # Contract scope uses the concrete contract identifier when available
    return getattr(cluster, "option_symbol", None) or f"{cluster.underlying}-{cluster.expiry.date()}-{cluster.strike}-{cluster.call_put}"


class CooldownManager:
    def __init__(self, cooldown_seconds: int, scope: str = "contract"):
        self.cooldown = timedelta(seconds=cooldown_seconds)
        self.scope = (scope or "contract").lower()
        if self.scope == "ticker":
            self.scope = "contract"
        self.cache: Dict[str, dict] = {}

    def should_suppress(self, cluster, score: float) -> tuple[bool, str, float | None, dict]:
        key = cluster_key(cluster, self.scope)
        state = self.cache.get(key)
        now = datetime.utcnow()
        meta = {
            "cooldown_key": key,
            "cooldown_last_sent_ts": state["ts"].isoformat() if state else None,
            "cooldown_window_seconds": int(self.cooldown.total_seconds()),
        }
        if not state or state.get("decision") != "sent":
            return False, "no_history", None, meta

        delta = now - state["ts"]
        improved = score >= state["score"] + 1.0 or getattr(cluster, "premium_total", 0) >= state.get("premium", 0) * 2
        if delta < self.cooldown and not improved:
            remaining = max(self.cooldown - delta, timedelta(seconds=0)).total_seconds()
            meta["cooldown_remaining_seconds"] = remaining
            return True, "cooldown", remaining, meta

        return False, "refresh", None, meta

    def mark_sent(self, cluster, score: float) -> None:
        key = cluster_key(cluster, self.scope)
        now = datetime.utcnow()
        self.cache[key] = {
            "ts": now,
            "score": score,
            "premium": getattr(cluster, "premium_total", 0),
            "decision": "sent",
        }
