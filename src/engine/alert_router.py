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

    def process_clusters(
        self,
        clusters: List,
        gamma_dte_max: int,
        structural_dte_min: int,
        logger=None,
        send_alerts: bool = True,
    ) -> dict:
        log = logger or self.logger
        sent = 0
        suppressed = 0
        suppressed_below = 0
        suppressed_cooldown = 0
        suppressed_quota = 0
        qualifying = 0
        sent_for_ticker = False if self.config.scan.allow_one_alert_per_ticker else None
        for cluster in clusters:
            setup = classify_cluster(cluster, gamma_dte_max, structural_dte_min)
            score, components, tags = score_cluster(
                cluster, quotes_penalty=self.config.scan.quotes_mode_score_penalty
            )
            suppress, reason, cooldown_remaining, cooldown_meta = self.cooldown.should_suppress(cluster, score)
            threshold = self.config.scan.alert_score_threshold
            evaluation_log = log.bind(
                stage="alert_evaluated",
                ticker=cluster.underlying,
                contract=cluster.option_symbol,
                contract_id=cluster.option_symbol,
                score=score,
                threshold=threshold,
                cluster_size=cluster.prints_count,
                cluster_window_seconds=self.config.scan.cluster_window_seconds,
                top_factors=[
                    {"name": name, "value": value}
                    for name, value in sorted(components.items(), key=lambda item: item[1], reverse=True)
                ]
                or [{"name": "unknown", "value": 0}],
                cooldown_key=cooldown_meta.get("cooldown_key"),
                cooldown_last_sent_ts=cooldown_meta.get("cooldown_last_sent_ts"),
                cooldown_window_seconds=cooldown_meta.get("cooldown_window_seconds"),
                mode=cluster.data_mode,
                notional_basis=getattr(cluster, "notional_basis", None),
            )

            if score < threshold:
                evaluation_log.info(
                    "alert suppressed",
                    decision="suppress",
                    suppress_reason="below_threshold",
                    cooldown_remaining_seconds=None,
                )
                suppressed += 1
                suppressed_below += 1
                continue

            qualifying += 1

            if sent_for_ticker and self.config.scan.allow_one_alert_per_ticker:
                evaluation_log.info(
                    "alert suppressed",
                    decision="suppress",
                    suppress_reason="ticker_limit",
                    cooldown_remaining_seconds=None,
                )
                suppressed += 1
                suppressed_quota += 1
                continue

            if suppress:
                evaluation_log.info(
                    "alert suppressed",
                    decision="suppress",
                    suppress_reason=reason,
                    cooldown_remaining_seconds=cooldown_remaining,
                )
                suppressed += 1
                suppressed_cooldown += 1
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
            if send_alerts:
                alert_id = self.repo.save_alert(
                    cluster, setup, score, components, tags, payload["template"]
                )
                self.messenger.send(payload)
                self.cooldown.mark_sent(cluster, score)
                sent += 1
                if self.config.scan.allow_one_alert_per_ticker:
                    sent_for_ticker = True
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
            else:
                suppressed += 1
                evaluation_log.info(
                    "alert skipped",
                    decision="skip",
                    suppress_reason="dry_run",
                    cooldown_remaining_seconds=None,
                    alert_id=None,
                    score=score,
                    setup=setup,
                    template=payload["template"],
                )
        return {
            "sent": sent,
            "suppressed": suppressed,
            "suppressed_below_threshold": suppressed_below,
            "suppressed_cooldown": suppressed_cooldown,
            "suppressed_quota": suppressed_quota,
            "qualifying": qualifying,
        }
