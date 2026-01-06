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
from src.utils.logging import get_logger, log_event, set_run_id


def run_once(
    ticker: str,
    client: MassiveClient,
    discovery: ContractDiscovery,
    matcher: TradeQuoteMatcher,
    cluster_builder: ClusterBuilder,
    router: AlertRouter,
    config,
    log,
    scan_id: str,
    send_alerts: bool,
):
    contracts = discovery.contracts_for(ticker)
    contracts_discovered = len(contracts)
    if not contracts:
        log_event(log, "candidates", trades=0, contracts=0, ticker=ticker)
        stage_counts = dict(
            contracts_discovered=contracts_discovered,
            contracts_after_filters=contracts_discovered,
            snapshots_fetched=0,
            snapshots_missing=0,
            trades_fetched=0,
            clusters_built=0,
            clusters_scored=0,
            alerts_sent=0,
            alerts_suppressed=0,
            alerts_deduped=0,
        )
        log.info(
            "ticker_scan_summary",
            scan_id=scan_id,
            ticker=ticker,
            stage_counts=stage_counts,
            reason="no_contracts",
        )
        return {"clusters": 0, "sent": 0, "suppressed": 0, "stage_counts": stage_counts}
    clusters_accum = []
    snapshots_fetched = 0
    snapshots_missing = 0
    trades_fetched = 0
    now = now_tz()
    start_window = now - timedelta(minutes=config.scan.max_lookback_minutes)
    for option_symbol in contracts:
        snapshot = client.get_contract_snapshot(ticker, option_symbol)
        if not snapshot:
            snapshots_missing += 1
            log.debug(
                "contract_snapshot_missing",
                ticker=ticker,
                option_symbol=option_symbol,
                mode="snapshot_lookup",
            )
            continue
        snapshots_fetched += 1
        trades = client.get_option_trades(option_symbol, start_window, now)
        trades_fetched += len(trades)
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
        log.debug(
            "contract_data_fetched",
            ticker=ticker,
            option_symbol=option_symbol,
            trades_count=len(trades),
            used_quotes_fallback=not bool(trades),
            snapshot_has_last_trade=bool(snapshot.last_trade),
            snapshot_day_volume=snapshot.day_volume,
            snapshot_oi=snapshot.oi,
        )
        log.debug(
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
            log.debug(
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
                log.debug(
                    "no_trades_for_contract",
                    ticker=ticker,
                    option_symbol=option_symbol,
                )
        clusters_accum.extend([c for c in clusters if c])
        if clusters:
            top_cluster = max(clusters, key=lambda c: c.premium_total)
            log.debug(
                "cluster_summary",
                option_symbol=option_symbol,
                clusters_built=len(clusters),
                top_cluster_notional=top_cluster.premium_total,
                top_cluster_trades=top_cluster.prints_count,
                mode=top_cluster.data_mode,
                notional_basis=getattr(top_cluster, "notional_basis", None),
            )
        log.debug(
            "clusters_built",
            ticker=ticker,
            option_symbol=option_symbol,
            clusters_count=len(clusters),
            prints_total=sum(c.prints_count for c in clusters if c),
            lookback_start_iso=start_window.isoformat(),
            lookback_end_iso=now.isoformat(),
        )
    log.debug(
        "cluster_build",
        ticker=ticker,
        candidates=len(contracts),
        clusters=len(clusters_accum),
    )
    result = router.process_clusters(
        clusters_accum,
        config.scan.gamma_dte_max,
        config.scan.structural_dte_min,
        log,
        send_alerts=send_alerts,
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
    alerts_sent = result.get("sent", 0)
    alerts_suppressed = result.get("suppressed", 0)
    alerts_deduped = result.get("suppressed_cooldown", 0)
    clusters_built = len(clusters_accum)
    clusters_scored = clusters_built
    reason = None
    if alerts_sent == 0:
        if contracts_discovered == 0:
            reason = "no_contracts"
        elif snapshots_fetched == 0:
            reason = "no_snapshots"
        elif trades_fetched == 0:
            reason = "no_trades"
        elif clusters_built == 0:
            reason = "no_clusters"
        elif alerts_deduped:
            reason = "cooldown"
        elif result.get("suppressed_quota", 0):
            reason = "quota"
        elif result.get("suppressed_below_threshold", 0) >= clusters_built:
            reason = "below_threshold"
    stage_counts = dict(
        contracts_discovered=contracts_discovered,
        contracts_after_filters=contracts_discovered,
        snapshots_fetched=snapshots_fetched,
        snapshots_missing=snapshots_missing,
        trades_fetched=trades_fetched,
        clusters_built=clusters_built,
        clusters_scored=clusters_scored,
        alerts_sent=alerts_sent,
        alerts_suppressed=alerts_suppressed,
        alerts_deduped=alerts_deduped,
    )
    summary_fields = dict(scan_id=scan_id, ticker=ticker, stage_counts=stage_counts)
    if alerts_sent == 0 and reason:
        summary_fields["reason"] = reason
    if not send_alerts and alerts_sent == 0:
        summary_fields.setdefault("reason", "dry_run")
    log.info("ticker_scan_summary", **summary_fields)
    top_premium = max([c.premium_total for c in clusters_accum], default=0)
    log.debug(
        "scoring",
        ticker=ticker,
        top_score=top_premium,
    )
    result_with_summary = dict(result)
    result_with_summary["stage_counts"] = stage_counts
    return result_with_summary


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
    last_market_state: tuple[bool, str, str] | None = None
    dry_run_cycle_completed = False
    while True:
        try:
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
            log.info(
                "market_status",
                is_open=is_open,
                reason=window_reason,
                next_transition_local_iso=next_transition_local_iso,
                seconds_until_transition=seconds_until_transition,
                next_scan_in_seconds=next_scan_in_seconds,
            )
            current_state = (is_open, window_reason, next_transition_local_iso)
            state_changed = current_state != last_market_state
            market_event = "market_window_state_change" if state_changed else "market_window_check"
            market_log_func = log.info if state_changed else log.debug
            market_log_func(
                market_event,
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
            last_market_state = current_state

            run_scan = is_open or (
                config.dry_run_ignore_market_window and not dry_run_cycle_completed
            )
            is_dry_run = config.dry_run_ignore_market_window and not is_open
            if not run_scan:
                # State transitions are already logged via market_window_* events.
                time.sleep(next_scan_in_seconds)
                continue

            scan_id = uuid.uuid4().hex[:8]
            set_run_id(scan_id)
            iteration_log = log.bind(run_id=scan_id, scan_id=scan_id)
            scan_start = time.monotonic()
            tickers_scanned = 0
            triggered = 0
            errors = 0
            log.info(
                "scan_cycle_start",
                scan_id=scan_id,
                now_local=now.isoformat(),
                now_utc=now.astimezone(timezone.utc).isoformat(),
                universe_count=len(config.scan.tickers),
                scan_interval_seconds=config.scan.scan_interval_seconds,
                dry_run=is_dry_run,
            )
            for ticker in config.scan.tickers:
                tickers_scanned += 1
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
                        scan_id,
                        send_alerts=is_open,
                    )
                    triggered += result.get("sent", 0)
                except Exception as exc:  # noqa: BLE001
                    ticker_log.error(
                        "ticker_scan_error",
                        scan_id=scan_id,
                        ticker=ticker,
                        error=str(exc),
                        exc_info=True,
                    )
                    stage_counts = dict(
                        contracts_discovered=0,
                        contracts_after_filters=0,
                        snapshots_fetched=0,
                        snapshots_missing=0,
                        trades_fetched=0,
                        clusters_built=0,
                        clusters_scored=0,
                        alerts_sent=0,
                        alerts_suppressed=0,
                        alerts_deduped=0,
                    )
                    ticker_log.info(
                        "ticker_scan_summary",
                        scan_id=scan_id,
                        ticker=ticker,
                        stage_counts=stage_counts,
                        reason="api_error",
                    )
                    errors += 1
            duration_ms = int((time.monotonic() - scan_start) * 1000)
            log.info(
                "scan_cycle_end",
                scan_id=scan_id,
                duration_ms=duration_ms,
                tickers_scanned=tickers_scanned,
                total_alerts_sent=triggered,
                total_errors=errors,
                dry_run=is_dry_run,
            )
            if is_open:
                log.info(
                    "scan_rollup",
                    tickers_scanned=tickers_scanned,
                    total_alerts_sent=triggered,
                    total_errors=errors,
                    duration_ms=duration_ms,
                )
            set_run_id(None)
            if is_dry_run:
                dry_run_cycle_completed = True
            time.sleep(config.scan.scan_interval_seconds)
        except Exception as exc:  # noqa: BLE001
            log.error("worker_loop_error", error=str(exc), exc_info=True)
            time.sleep(config.scan.scan_interval_seconds)


if __name__ == "__main__":
    main()
