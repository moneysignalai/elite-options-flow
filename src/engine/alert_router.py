from typing import List

from src.engine.classify import classify_cluster
from src.engine.score import score_cluster
from src.engine.dedupe import CooldownManager
from src.engine.templates import render_alert
from src.messaging.telegram import TelegramMessenger
from src.storage.repository import AlertRepository
from src.utils.logging import get_logger


class AlertRouter:
    def __init__(self, repo: AlertRepository, messenger: TelegramMessenger, cooldown: CooldownManager, config, logger=None):
        self.repo = repo
        self.messenger = messenger
        self.cooldown = cooldown
        self.config = config
        self.logger = logger or get_logger("app")

    def process_clusters(self, clusters: List, gamma_dte_max: int, structural_dte_min: int, logger=None) -> dict:
        log = logger or self.logger
        sent = 0
        suppressed = 0
        for cluster in clusters:
            setup = classify_cluster(cluster, gamma_dte_max, structural_dte_min)
            score, components, tags = score_cluster(cluster)
            suppress, reason, cooldown_remaining = self.cooldown.should_suppress(cluster, score)

            evaluation_log = log.bind(
                stage="alert_evaluated",
                ticker=cluster.underlying,
                contract=cluster.option_symbol,
                contract_id=cluster.option_symbol,
                score=score,
                threshold=self.config.scan.alert_score_threshold,
                cluster_size=cluster.prints_count,
                cluster_window_seconds=self.config.scan.cluster_window_seconds,
                top_factors=[
                    {"name": name, "value": value}
                    for name, value in sorted(components.items(), key=lambda item: item[1], reverse=True)
                ]
                or [{"name": "unknown", "value": 0}],
            )

            if score < self.config.scan.alert_score_threshold:
                evaluation_log.info(
                    "alert suppressed",
                    decision="suppress",
                    suppress_reason="below_threshold",
                    cooldown_remaining_seconds=None,
                )
                suppressed += 1
                continue
            if suppress:
                evaluation_log.info(
                    "alert suppressed",
                    decision="suppress",
                    suppress_reason=reason,
                    cooldown_remaining_seconds=cooldown_remaining,
                )
                suppressed += 1
                continue
            payload = render_alert(
                cluster,
                setup,
                score,
                components,
                tags,
                {
                    "deep": self.config.scan.deep_dive_threshold,
                    "medium": self.config.scan.medium_threshold,
                },
            )
            alert_id = self.repo.save_alert(cluster, setup, score, components, tags, payload["template"])
            self.messenger.send(payload)
            sent += 1
            evaluation_log.info(
                "alert sent",
                decision="send",
                suppress_reason=None,
                cooldown_remaining_seconds=None,
                alert_id=alert_id,
                score=score,
                setup=setup,
                template=payload["template"],
            )
        return {"sent": sent, "suppressed": suppressed}
