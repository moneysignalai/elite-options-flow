from datetime import datetime, timedelta
from typing import Dict


def cluster_key(cluster) -> str:
    return f"{cluster.underlying}-{cluster.expiry.date()}-{cluster.strike}-{cluster.call_put}"


class CooldownManager:
    def __init__(self, cooldown_minutes: int):
        self.cooldown = timedelta(minutes=cooldown_minutes)
        self.cache: Dict[str, dict] = {}

    def should_suppress(self, cluster, score: float) -> tuple[bool, str]:
        key = cluster_key(cluster)
        state = self.cache.get(key)
        now = datetime.utcnow()
        if not state:
            self.cache[key] = {"ts": now, "score": score, "premium": cluster.premium_total}
            return False, "new"
        delta = now - state["ts"]
        improved = score >= state["score"] + 1.0 or cluster.premium_total >= state["premium"] * 2
        if delta < self.cooldown and not improved:
            return True, "cooldown"
        self.cache[key] = {"ts": now, "score": score, "premium": cluster.premium_total}
        return False, "refresh"
