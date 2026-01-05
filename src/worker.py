import os
import time
import uuid
from datetime import timezone, timedelta

from src.config import load_config, validate_config
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
    log_event(log, "contracts_discovered", ticker=ticker, contracts_count=len(contracts))
    log_event(
        log,
        "snapshot_summary",
        ticker=ticker,
        returned_count=len(contracts),
    )
    if not contracts:
        log_event(log, "candidates", trades=0, contracts=0, ticker=ticker)
        return {"clusters": 0, "sent": 0, "suppressed": 0}
    clusters_accum = []
    now = now_tz()
    start_window = now - timedelta(minutes=config.scan.max_lookback_minutes)
    for option_symbol in contracts:
        snapshot = client.get_contract_snapshot(ticker, option_symbol)
        if not snapshot:
            log_event(
                log,
                "contract_snapshot_missing",
                ticker=ticker,
                option_symbol=option_symbol,
                mode="snapshot_lookup",
            )
            continue
        trades = client.get_option_trades(option_symbol, start_window, now)
        quotes = [snapshot.last_quote] if snapshot.last_quote else []
        has_snapshot_signal = bool(snapshot.last_trade or snapshot.day_volume or snapshot.oi)
        mode = "trades" if trades else "quotes_fallback"
        reason = (
            "trade_endpoint"
            if trades
            else "snapshot_last_trade"
            if snapshot.last_trade
            else "snapshot_liquidity" if has_snapshot_signal else "no_trades_available"
        )
        if not quotes:
            quotes = client.get_option_quotes(option_symbol)
        log_event(
            log,
            "contract_data_fetched",
            ticker=ticker,
            option_symbol=option_symbol,
            trades_count=len(trades),
            used_quotes_fallback=not bool(trades),
            snapshot_has_last_trade=bool(snapshot.last_trade),
            snapshot_day_volume=snapshot.day_volume,
            snapshot_oi=snapshot.oi,
        )
        log_event(
            log,
            "contract_mode_selected",
            ticker=ticker,
            option_symbol=option_symbol,
            mode=mode,
            reason=reason,
            trades_count=len(trades),
            quotes_count=len(quotes),
            day_volume=snapshot.day_volume,
            oi=snapshot.oi,
        )
        if not trades:
            log_event(
                log,
                "quotes_fallback_used",
                ticker=ticker,
                option_symbol=option_symbol,
                quotes_count=len(quotes),
            )
        if trades:
            labeled = matcher.label_aggression(trades, quotes)
            clusters = cluster_builder.build(labeled, snapshot)
        else:
            fallback_cluster = cluster_builder.build_snapshot_cluster(
                snapshot, quotes, mode=mode
            )
            clusters = [fallback_cluster] if fallback_cluster else []
            if not fallback_cluster:
                log_event(
                    log,
                    "no_trades_for_contract",
                    ticker=ticker,
                    option_symbol=option_symbol,
                )
        clusters_accum.extend([c for c in clusters if c])
        if clusters:
            top_cluster = max(clusters, key=lambda c: c.premium_total)
            log_event(
                log,
                "cluster_summary",
                option_symbol=option_symbol,
                clusters_built=len(clusters),
                top_cluster_notional=top_cluster.premium_total,
                top_cluster_trades=top_cluster.prints_count,
                mode=top_cluster.data_mode,
                notional_basis=getattr(top_cluster, "notional_basis", None),
            )
        log_event(
            log,
            "clusters_built",
            ticker=ticker,
            option_symbol=option_symbol,
            clusters_count=len(clusters),
            prints_total=sum(c.prints_count for c in clusters if c),
            lookback_start_iso=start_window.isoformat(),
            lookback_end_iso=now.isoformat(),
        )
    log.info(
        "cluster_build",
        ticker=ticker,
        candidates=len(contracts),
        clusters=len(clusters_accum),
    )
    result = router.process_clusters(
        clusters_accum, config.scan.gamma_dte_max, config.scan.structural_dte_min, log
    )
    log_event(
        log,
        "alert_routing_summary",
        ticker=ticker,
        clusters=len(clusters_accum),
        sent=result.get("sent", 0),
        suppressed=result.get("suppressed", 0),
        suppressed_reasons_breakdown={
            "below_threshold": result.get("suppressed_below_threshold", 0),
            "cooldown": result.get("suppressed_cooldown", 0),
            "quota": result.get("suppressed_quota", 0),
        },
        qualifying=result.get("qualifying", 0),
    )
    top_premium = max([c.premium_total for c in clusters_accum], default=0)
    log.info(
        "scoring",
        ticker=ticker,
        top_score=top_premium,
    )
    return result


def main():
    log = get_logger("worker")
    config = load_config()
    validate_config(config, log)
    client = MassiveClient(config, logger=log)
    discovery = ContractDiscovery(client, config.scan.chain_discovery)
    matcher = TradeQuoteMatcher(config.scan.aggression_window_seconds)
    cluster_builder = ClusterBuilder(
        config.scan.cluster_window_seconds,
        quotes_notional_cap=config.scan.quotes_mode_notional_cap,
        quotes_min_oi=config.scan.quotes_mode_require_min_oi,
    )
    cooldown = CooldownManager(
        config.scan.alert_cooldown_seconds, scope=config.scan.cooldown_scope
    )
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
    last_is_open: bool | None = None
    last_window_reason: str | None = None
    while True:
        if not config.scan.tickers:
            log_event(
                log,
                "scan_config_invalid",
                tickers=config.scan.tickers,
                raw_tickers=os.getenv("SCAN_TICKERS", ""),
            )
            time.sleep(sleep_seconds(True, config.scan.scan_interval_seconds))
            continue

        now = now_tz()
        (
            is_open,
            window_reason,
            next_transition_local,
            seconds_until_transition,
        ) = within_window(
            now,
            config.scan.rth_start,
            config.scan.rth_end,
            config.scan.enable_premarket,
            config.scan.enable_afterhours,
        )
        next_transition_local_iso = next_transition_local.isoformat()
        next_scan_in_seconds = sleep_seconds(
            outside=not is_open, interval=config.scan.scan_interval_seconds
        )
        state_changed = (
            last_is_open is None
            or is_open != last_is_open
            or window_reason != last_window_reason
        )
        market_log_func = log.info if state_changed else log.debug
        market_log_func(
            "market_window_check",
            event="market_window_check",
            now_local=now.isoformat(),
            now_utc=now.astimezone(timezone.utc).isoformat(),
            market_tz="America/New_York",
            rth_start=config.scan.rth_start,
            rth_end=config.scan.rth_end,
            enable_premarket=config.scan.enable_premarket,
            enable_afterhours=config.scan.enable_afterhours,
            is_open=is_open,
            reason=window_reason,
            next_transition_time=next_transition_local_iso,
            seconds_until_transition=seconds_until_transition,
            next_scan_in_seconds=next_scan_in_seconds,
        )
        last_is_open = is_open
        last_window_reason = window_reason
        if not is_open:
            skip_log_func = log.info if state_changed else log.debug
            skip_log_func(
                "scan_skipped",
                event="scan_skipped",
                now=now.isoformat(),
                reason=window_reason,
                next_transition_local_iso=next_transition_local_iso,
                seconds_until_transition=seconds_until_transition,
                next_scan_in_seconds=next_scan_in_seconds,
            )
            time.sleep(next_scan_in_seconds)
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
            "scan_iteration_start",
            universe_count=len(config.scan.tickers),
            scan_interval_seconds=config.scan.scan_interval_seconds,
            max_lookback_minutes=config.scan.max_lookback_minutes,
            window="rth"
            if not (config.scan.enable_afterhours or config.scan.enable_premarket)
            else "extended",
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
