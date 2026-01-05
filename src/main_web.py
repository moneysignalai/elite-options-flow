import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from datetime import datetime

from src.config import load_config, validate_config
from src.storage.db import init_engine, get_session_factory
from src.storage.repository import AlertRepository
from src.messaging.telegram import TelegramMessenger
from src.engine.dedupe import CooldownManager
from src.engine.alert_router import AlertRouter
from src.massive.client import MassiveClient
from src.engine.discovery import ContractDiscovery
from src.engine.ingest import TradeQuoteMatcher
from src.engine.cluster import ClusterBuilder
from src.engine.templates import render_alert
from src.engine.classify import classify_cluster
from src.engine.score import score_cluster
from src.utils.time import now_tz
from src.utils.logging import get_logger, log_error, log_event, set_request_id

logger = get_logger("web")
config = load_config()
validate_config(config, logger)

# setup repo
session_factory = None
if config.database_url:
    engine = init_engine(config.database_url)
    session_factory = get_session_factory(engine)
else:
    log_event(logger, "db_disabled")
repo = AlertRepository(session_factory=session_factory, logger=logger)
messenger = TelegramMessenger(config.telegram.bot_token, config.telegram.chat_id, logger=logger)
cooldown = CooldownManager(config.scan.cooldown_minutes)
massive_client = MassiveClient(config, logger=logger)
discovery = ContractDiscovery(massive_client, config.scan.chain_discovery)
matcher = TradeQuoteMatcher(config.scan.aggression_window_seconds)
cluster_builder = ClusterBuilder(config.scan.cluster_window_seconds)
router = AlertRouter(repo, messenger, cooldown, config, logger=logger)

app = FastAPI()


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = uuid.uuid4().hex[:8]
    set_request_id(request_id)
    request_log = logger.bind(request_id=request_id, path=request.url.path, method=request.method)
    request.state.logger = request_log
    request.state.request_id = request_id
    start = time.time()
    try:
        response = await call_next(request)
    except Exception as exc:  # noqa: BLE001
        log_error(request_log, "request_handler", exc)
        set_request_id(None)
        raise
    latency_ms = int((time.time() - start) * 1000)
    log_event(
        request_log,
        "request_complete",
        status_code=response.status_code,
        latency_ms=latency_ms,
    )
    set_request_id(None)
    return response


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/status")
async def status():
    return {
        "tickers": config.scan.tickers,
        "chain_discovery": config.scan.chain_discovery,
        "database": bool(config.database_url),
        "cooldown_minutes": config.scan.cooldown_minutes,
    }


@app.get("/alerts/recent")
async def recent_alerts(limit: int = 100):
    return repo.recent_alerts(limit=limit)


@app.post("/debug/force-alert")
async def force_alert(ticker: str, request: Request):
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker required")
    # simple flow: use discovery to get contracts and process first
    contracts = discovery.contracts_for(ticker)
    if not contracts:
        return JSONResponse({"status": "suppressed", "reason": "no_contracts"})
    request_log = getattr(request.state, "logger", logger)
    option_symbol = contracts[0]
    snapshot = massive_client.get_contract_snapshot(ticker, option_symbol)
    if not snapshot or not snapshot.last_trade:
        return JSONResponse({"status": "suppressed", "reason": "no_trades"})
    trades = [snapshot.last_trade]
    quotes = [snapshot.last_quote] if snapshot.last_quote else []
    labeled = matcher.label_aggression(trades, quotes)
    clusters = cluster_builder.build(labeled, snapshot)
    result = router.process_clusters(
        clusters,
        gamma_dte_max=config.scan.gamma_dte_max,
        structural_dte_min=config.scan.structural_dte_min,
        logger=request_log,
    )
    return result


@app.post("/admin/reload-config")
async def reload_config(request: Request):
    global config
    config = load_config()
    req_log = getattr(request.state, "logger", logger)
    log_event(req_log, "config_reloaded", tickers=config.scan.tickers)
    return {"status": "reloaded", "tickers": config.scan.tickers}
