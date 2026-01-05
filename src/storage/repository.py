import json
import time
from datetime import datetime
from collections import deque
from typing import List

from src.utils.logging import get_logger, log_error, log_event

from src.storage import models
from src.engine.dedupe import cluster_key


class AlertRepository:
    def __init__(self, session_factory=None, memory_limit: int = 500, logger=None):
        self.session_factory = session_factory
        self.memory_alerts = deque(maxlen=memory_limit)
        self.memory_dedupe = {}
        self.logger = logger or get_logger("app")

    def save_alert(self, cluster, setup: str, score: float, components: dict, tags: list, template: str):
        key = cluster_key(cluster)
        record = {
            "ts": datetime.utcnow(),
            "underlying": cluster.underlying,
            "option_ticker": cluster.option_symbol,
            "call_put": cluster.call_put,
            "strike": cluster.strike,
            "expiry": cluster.expiry.date(),
            "dte": cluster.dte,
            "premium_total": cluster.premium_total,
            "contracts_total": cluster.contracts_total,
            "prints_count": cluster.prints_count,
            "duration_sec": cluster.duration_sec,
            "ask_side_ratio": cluster.ask_side_ratio,
            "sweep_score": cluster.sweep_score,
            "oi": cluster.oi,
            "vol_oi_ratio": cluster.contracts_total / max(cluster.oi or cluster.contracts_total, 1),
            "otm_pct": cluster.otm_pct,
            "setup_type": setup,
            "score_total": score,
            "score_components": components,
            "tags": tags,
            "template_type": template,
            "cluster_key": key,
        }
        if self.session_factory:
            session = self.session_factory()
            start = time.time()
            try:
                alert = models.Alert(
                    ts=record["ts"],
                    underlying=record["underlying"],
                    option_ticker=record["option_ticker"],
                    call_put=record["call_put"],
                    strike=record["strike"],
                    expiry=record["expiry"],
                    dte=record["dte"],
                    premium_total=record["premium_total"],
                    contracts_total=record["contracts_total"],
                    prints_count=record["prints_count"],
                    duration_sec=record["duration_sec"],
                    ask_side_ratio=record["ask_side_ratio"],
                    sweep_score=record["sweep_score"],
                    oi=record["oi"],
                    vol_oi_ratio=record["vol_oi_ratio"],
                    otm_pct=record["otm_pct"],
                    setup_type=record["setup_type"],
                    score_total=record["score_total"],
                    score_components_json=json.dumps(components),
                    tags_json=json.dumps(tags),
                    template_type=template,
                    cluster_key=key,
                )
                session.add(alert)
                session.merge(
                    models.DedupeState(
                        cluster_key=key,
                        last_alert_ts=record["ts"],
                        last_score=score,
                        last_premium=cluster.premium_total,
                    )
                )
                session.commit()
                duration_ms = int((time.time() - start) * 1000)
                log_event(
                    self.logger,
                    "db_write",
                    table="alerts",
                    alert_id=alert.id,
                    duration_ms=duration_ms,
                    success=True,
                )
                log_event(
                    self.logger,
                    "alert_persisted",
                    alert_id=alert.id,
                    ticker=cluster.underlying,
                    option_symbol=cluster.option_symbol,
                    score=score,
                    template=template,
                    sent_ts=record["ts"].isoformat(),
                )
                return alert.id
            except Exception as exc:  # noqa: BLE001
                log_error(self.logger, "save_alert", exc)
                raise
            finally:
                session.close()
        else:
            self.memory_alerts.append(record)
            self.memory_dedupe[key] = {
                "last_alert_ts": record["ts"],
                "last_score": score,
                "last_premium": cluster.premium_total,
            }
            log_event(
                self.logger,
                "alert_persisted",
                alert_id=len(self.memory_alerts),
                ticker=cluster.underlying,
                option_symbol=cluster.option_symbol,
                score=score,
                template=template,
                sent_ts=record["ts"].isoformat(),
            )
            return len(self.memory_alerts)

    def recent_alerts(self, limit: int = 100) -> List[dict]:
        if self.session_factory:
            session = self.session_factory()
            try:
                q = session.query(models.Alert).order_by(models.Alert.ts.desc()).limit(limit)
                return [self._to_dict(a) for a in q]
            finally:
                session.close()
        return list(self.memory_alerts)[-limit:][::-1]

    def dedupe_state(self, key: str):
        if self.session_factory:
            session = self.session_factory()
            try:
                return session.query(models.DedupeState).filter_by(cluster_key=key).first()
            finally:
                session.close()
        return self.memory_dedupe.get(key)

    @staticmethod
    def _to_dict(alert: models.Alert) -> dict:
        return {
            "id": alert.id,
            "ts": alert.ts.isoformat(),
            "underlying": alert.underlying,
            "option_ticker": alert.option_ticker,
            "call_put": alert.call_put,
            "strike": alert.strike,
            "expiry": alert.expiry.isoformat(),
            "dte": alert.dte,
            "premium_total": alert.premium_total,
            "contracts_total": alert.contracts_total,
            "prints_count": alert.prints_count,
            "duration_sec": alert.duration_sec,
            "ask_side_ratio": alert.ask_side_ratio,
            "sweep_score": alert.sweep_score,
            "oi": alert.oi,
            "vol_oi_ratio": alert.vol_oi_ratio,
            "otm_pct": alert.otm_pct,
            "setup_type": alert.setup_type,
            "score_total": alert.score_total,
            "score_components": json.loads(alert.score_components_json),
            "tags": json.loads(alert.tags_json),
            "template_type": alert.template_type,
            "cluster_key": alert.cluster_key,
        }
