from typing import Dict
from src.engine.cluster import FlowCluster


def score_cluster(cluster: FlowCluster, quotes_penalty: float = 0.75) -> tuple[float, Dict[str, float], list[str]]:
    components = {}
    tags = []
    # size/premium
    premium_score = min(4.0, cluster.premium_total / 250000)
    components["size"] = premium_score
    # vol vs oi
    oi_denominator = cluster.oi if (cluster.oi or 0) > 0 else max(cluster.contracts_total, 1)
    vol_oi_ratio = cluster.contracts_total / oi_denominator
    components["vol_oi"] = min(2.0, vol_oi_ratio)
    # aggression
    components["aggression"] = cluster.ask_side_ratio * 2
    if cluster.ask_side_ratio > 0.7:
        tags.append("aggressive")
    # clustering
    components["clustering"] = min(2.0, cluster.sweep_score * 2)
    # structure
    structure = 0.0
    if cluster.dte <= 3:
        structure += 1.0
    if (cluster.otm_pct or 0) >= 5:
        structure += 0.5
    components["structure"] = structure
    # repeats placeholder
    components["repeats"] = 0.5 if cluster.prints_count > 3 else 0.0
    if cluster.data_mode == "trades":
        components["mode"] = 0.5
    elif cluster.data_mode == "snapshot":
        components["mode"] = 0.25
        tags.append("snapshot_based")
    else:
        components["mode"] = 0.1
        tags.append("quote_based")

    total = sum(components.values())
    if cluster.data_mode == "quotes_fallback":
        total *= quotes_penalty
    if total > 10:
        total = 10.0
    return total, components, tags
