import argparse

from src.config import load_config, validate_config
from src.engine.alert_router import AlertRouter
from src.engine.cluster import ClusterBuilder
from src.engine.discovery import ContractDiscovery
from src.engine.dedupe import CooldownManager
from src.engine.ingest import TradeQuoteMatcher
from src.logging_setup import setup_logging
from src.massive.client import MassiveClient
from src.messaging.telegram import TelegramMessenger
from src.storage.db import init_engine, get_session_factory
from src.storage.repository import AlertRepository
from src.utils.logging import get_logger, set_run_id
from src.worker import run_once


def main():
    parser = argparse.ArgumentParser(description="Debug a single ticker run")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--limit_contracts", type=int, default=None)
    args = parser.parse_args()

    setup_logging()
    log = get_logger("debug_run")
    config = load_config()
    validate_config(config, log)

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
    repo = AlertRepository(session_factory=session_factory, logger=log)
    router = AlertRouter(repo, messenger, cooldown, config, logger=log)

    set_run_id("debug")
    if args.limit_contracts:
        original_contracts_for = discovery.contracts_for

        def limited_contracts(ticker):
            contracts = original_contracts_for(ticker)
            return contracts[: args.limit_contracts]

        discovery.contracts_for = limited_contracts  # type: ignore[assignment]

    result = run_once(
        args.ticker.upper(),
        client,
        discovery,
        matcher,
        cluster_builder,
        router,
        config,
        log,
    )

    log.info(
        "debug_run_complete",
        ticker=args.ticker.upper(),
        sent=result.get("sent"),
        suppressed=result.get("suppressed"),
        run_mode="manual",
    )


if __name__ == "__main__":
    main()
