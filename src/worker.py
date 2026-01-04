import time
from datetime import datetime, timedelta
from loguru import logger

from src.config import load_config
from src.logging_setup import configure_logging, get_logger
from src.massive.client import MassiveClient
from src.massive.models import OptionTrade
from src.engine.discovery import ContractDiscovery
from src.engine.ingest import TradeQuoteMatcher
from src.engine.cluster import ClusterBuilder
from src.engine.alert_router import AlertRouter
from src.engine.dedupe import CooldownManager
from src.messaging.telegram import TelegramMessenger
from src.storage.db import init_engine, get_session_factory
from src.storage.repository import AlertRepository
from src.utils.time import within_window, now_tz, sleep_seconds


def run_once(ticker: str, client: MassiveClient, discovery: ContractDiscovery, matcher: TradeQuoteMatcher, cluster_builder: ClusterBuilder, router: AlertRouter, config):
    logger.info("ticker start", ticker=ticker)
    contracts = discovery.contracts_for(ticker)
    if not contracts:
        logger.info("candidates", trades=0, contracts=0)
        return {"clusters": 0}
    clusters_accum = []
    for option_symbol in contracts:
        trades = client.get_option_trades(option_symbol)
        quotes = client.get_option_quotes(option_symbol)
        snapshot = client.get_option_snapshot(option_symbol)
        labeled = matcher.label_aggression(trades, quotes)
        clusters = cluster_builder.build(labeled, snapshot)
        clusters_accum.extend(clusters)
    logger.info("cluster build", candidates=len(contracts), clusters=len(clusters_accum))
    result = router.process_clusters(clusters_accum, config.scan.gamma_dte_max, config.scan.structural_dte_min)
    logger.info("scoring", top_score=max([c.premium_total for c in clusters_accum], default=0))
    return result


def main():
    configure_logging()
    log = get_logger()
    config = load_config()
    client = MassiveClient(config)
    discovery = ContractDiscovery(client, config.scan.chain_discovery)
    matcher = TradeQuoteMatcher(config.scan.aggression_window_seconds)
    cluster_builder = ClusterBuilder(config.scan.cluster_window_seconds)
    cooldown = CooldownManager(config.scan.cooldown_minutes)
    messenger = TelegramMessenger(config.telegram.bot_token, config.telegram.chat_id)

    session_factory = None
    if config.database_url:
        engine = init_engine(config.database_url)
        session_factory = get_session_factory(engine)
    repo = AlertRepository(session_factory=session_factory)
    router = AlertRouter(repo, messenger, cooldown, config)

    log.info("worker start", universe_count=len(config.scan.tickers))
    while True:
        now = now_tz()
        if not within_window(now, config.scan.rth_start, config.scan.rth_end, config.scan.enable_premarket, config.scan.enable_afterhours):
            log.info("outside_window", now=now.isoformat())
            time.sleep(sleep_seconds(True, config.scan.scan_interval_seconds))
            continue
        scan_start = time.time()
        triggered = 0
        suppressed = 0
        errors = 0
        for ticker in config.scan.tickers:
            try:
                result = run_once(ticker, client, discovery, matcher, cluster_builder, router, config)
                triggered += result.get("sent", 0)
                suppressed += result.get("suppressed", 0)
            except Exception as exc:  # noqa: BLE001
                log.exception("ticker error", ticker=ticker, error=str(exc))
                errors += 1
        duration_ms = int((time.time() - scan_start) * 1000)
        log.info("scan end", duration_ms=duration_ms, triggered=triggered, suppressed=suppressed, errors=errors)
        time.sleep(config.scan.scan_interval_seconds)


if __name__ == "__main__":
    main()
