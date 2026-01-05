import time
import uuid

from src.config import load_config
from src.massive.client import MassiveClient
from src.engine.discovery import ContractDiscovery
from src.engine.ingest import TradeQuoteMatcher
from src.engine.cluster import ClusterBuilder
from src.engine.alert_router import AlertRouter
from src.engine.dedupe import CooldownManager
from src.messaging.telegram import TelegramMessenger
from src.storage.db import init_engine, get_session_factory
from src.storage.repository import AlertRepository
from src.utils.time import within_window, now_tz, sleep_seconds
from src.utils.logging import get_logger, log_event, log_error, set_run_id


def run_once(
    ticker: str,
    client: MassiveClient,
    discovery: ContractDiscovery,
    matcher: TradeQuoteMatcher,
    cluster_builder: ClusterBuilder,
    router: AlertRouter,
    config,
    log,
):
    log_event(log, "ticker_start", ticker=ticker)
    contracts = discovery.contracts_for(ticker)
    if not contracts:
        log_event(log, "candidates", trades=0, contracts=0, ticker=ticker)
        return {"clusters": 0, "sent": 0, "suppressed": 0}
    clusters_accum = []
    for option_symbol in contracts:
        trades = client.get_option_trades(option_symbol)
        quotes = client.get_option_quotes(option_symbol)
        snapshot = client.get_option_snapshot(option_symbol)
        labeled = matcher.label_aggression(trades, quotes)
        clusters = cluster_builder.build(labeled, snapshot)
        clusters_accum.extend(clusters)
    log.info(
        "cluster_build",
        ticker=ticker,
        candidates=len(contracts),
        clusters=len(clusters_accum),
    )
    result = router.process_clusters(
        clusters_accum, config.scan.gamma_dte_max, config.scan.structural_dte_min, log
    )
    log.info(
        "scoring",
        ticker=ticker,
        top_score=max([c.premium_total for c in clusters_accum], default=0),
    )
    return result


def main():
    log = get_logger("worker")
    config = load_config()
    client = MassiveClient(config, logger=log)
    discovery = ContractDiscovery(client, config.scan.chain_discovery)
    matcher = TradeQuoteMatcher(config.scan.aggression_window_seconds)
    cluster_builder = ClusterBuilder(config.scan.cluster_window_seconds)
    cooldown = CooldownManager(config.scan.cooldown_minutes)
    messenger = TelegramMessenger(config.telegram.bot_token, config.telegram.chat_id, logger=log)

    session_factory = None
    if config.database_url:
        engine = init_engine(config.database_url)
        session_factory = get_session_factory(engine)
    else:
        log_event(log, "db_disabled")
    repo = AlertRepository(session_factory=session_factory, logger=log)
    router = AlertRouter(repo, messenger, cooldown, config, logger=log)

    log_event(log, "worker_start", universe_count=len(config.scan.tickers))
    while True:
        now = now_tz()
        if not within_window(
            now,
            config.scan.rth_start,
            config.scan.rth_end,
            config.scan.enable_premarket,
            config.scan.enable_afterhours,
        ):
            log_event(log, "scan_skipped", now=now.isoformat(), reason="outside_window")
            time.sleep(sleep_seconds(True, config.scan.scan_interval_seconds))
            continue

        run_id = uuid.uuid4().hex[:8]
        set_run_id(run_id)
        iteration_log = log.bind(run_id=run_id)
        scan_start = time.time()
        triggered = 0
        suppressed = 0
        errors = 0
        log_event(
            iteration_log,
            "scan_start",
            universe_count=len(config.scan.tickers),
            tickers=config.scan.tickers,
            window="rth" if not (config.scan.enable_afterhours or config.scan.enable_premarket) else "extended",
        )
        for ticker in config.scan.tickers:
            ticker_log = iteration_log.bind(ticker=ticker)
            try:
                result = run_once(
                    ticker,
                    client,
                    discovery,
                    matcher,
                    cluster_builder,
                    router,
                    config,
                    ticker_log,
                )
                triggered += result.get("sent", 0)
                suppressed += result.get("suppressed", 0)
            except Exception as exc:  # noqa: BLE001
                log_error(ticker_log, "run_once", exc)
                errors += 1
        duration_ms = int((time.time() - scan_start) * 1000)
        log_event(
            iteration_log,
            "scan_end",
            scanned_count=len(config.scan.tickers),
            candidates_count=triggered + suppressed,
            alerts_sent=triggered,
            alerts_suppressed=suppressed,
            errors_count=errors,
            duration_ms=duration_ms,
        )
        set_run_id(None)
        time.sleep(config.scan.scan_interval_seconds)


if __name__ == "__main__":
    main()
