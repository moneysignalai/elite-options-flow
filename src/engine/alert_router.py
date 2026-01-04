from typing import List
from loguru import logger

from src.engine.classify import classify_cluster
from src.engine.score import score_cluster
from src.engine.dedupe import CooldownManager, cluster_key
from src.engine.templates import render_alert
from src.messaging.telegram import TelegramMessenger
from src.storage.repository import AlertRepository


class AlertRouter:
    def __init__(self, repo: AlertRepository, messenger: TelegramMessenger, cooldown: CooldownManager, config):
        self.repo = repo
        self.messenger = messenger
        self.cooldown = cooldown
        self.config = config

    def process_clusters(self, clusters: List, gamma_dte_max: int, structural_dte_min: int) -> dict:
        sent = 0
        suppressed = 0
        for cluster in clusters:
            setup = classify_cluster(cluster, gamma_dte_max, structural_dte_min)
            score, components, tags = score_cluster(cluster)
            suppress, reason = self.cooldown.should_suppress(cluster, score)
            if score < self.config.scan.alert_score_threshold:
                logger.info("alert suppressed", reason="below_threshold", score=score, key=cluster_key(cluster))
                suppressed += 1
                continue
            if suppress:
                logger.info("alert suppressed", reason=reason, key=cluster_key(cluster))
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
            logger.info("alert sent", id=alert_id, score=score, setup=setup, template=payload["template"])
        return {"sent": sent, "suppressed": suppressed}
