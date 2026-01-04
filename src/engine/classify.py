from typing import List
from src.engine.cluster import FlowCluster


class SetupType:
    GAMMA_EXPANSION = "GAMMA_EXPANSION"
    STRUCTURAL_BUILD = "STRUCTURAL_BUILD"
    INFORMATIONAL = "INFORMATIONAL"
    HEDGE_SUPPRESS = "HEDGE_SUPPRESS"
    PINNING = "PINNING"


def classify_cluster(cluster: FlowCluster, gamma_dte_max: int, structural_dte_min: int) -> str:
    if cluster.dte <= gamma_dte_max and (cluster.otm_pct or 0) >= 5 and cluster.ask_side_ratio >= 0.6:
        return SetupType.GAMMA_EXPANSION
    if cluster.dte >= structural_dte_min and cluster.premium_total >= 200000 and cluster.ask_side_ratio < 0.6:
        return SetupType.STRUCTURAL_BUILD
    if cluster.prints_count > 5 and cluster.sweep_score > 0.5:
        return SetupType.INFORMATIONAL
    if cluster.ask_side_ratio < 0.4:
        return SetupType.HEDGE_SUPPRESS
    if cluster.dte <= 7 and abs(cluster.otm_pct or 0) < 2:
        return SetupType.PINNING
    return SetupType.INFORMATIONAL
