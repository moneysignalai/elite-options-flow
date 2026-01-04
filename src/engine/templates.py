from src.engine.classify import SetupType


def select_template(score: float, thresholds: dict[str, float]) -> str:
    if score >= thresholds.get("deep", 9.0):
        return "DEEP_DIVE"
    if score >= thresholds.get("medium", 7.0):
        return "MEDIUM"
    return "SHORT"


def render_alert(cluster, setup: str, score: float, components: dict, tags: list, thresholds: dict[str, float]) -> dict:
    template = select_template(score, thresholds)
    why = sorted(components.items(), key=lambda kv: kv[1], reverse=True)[:3]
    return {
        "template": template,
        "setup": setup,
        "score": round(score, 2),
        "why": [f"{k}:{v:.2f}" for k, v in why],
        "contract": f"{cluster.underlying} {cluster.expiry.date()} {cluster.strike} {cluster.call_put}",
        "premium_total": round(cluster.premium_total, 2),
        "contracts_total": cluster.contracts_total,
        "aggression": round(cluster.ask_side_ratio, 2),
        "vol_oi": cluster.contracts_total / max(cluster.oi or cluster.contracts_total, 1),
        "tags": tags,
    }
