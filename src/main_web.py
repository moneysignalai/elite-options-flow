from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime

from src.config import load_config
from src.logging_setup import configure_logging, get_logger
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

configure_logging()
logger = get_logger()
config = load_config()

# setup repo
session_factory = None
if config.database_url:
    engine = init_engine(config.database_url)
    session_factory = get_session_factory(engine)
repo = AlertRepository(session_factory=session_factory)
messenger = TelegramMessenger(config.telegram.bot_token, config.telegram.chat_id)
cooldown = CooldownManager(config.scan.cooldown_minutes)
massive_client = MassiveClient(config)
discovery = ContractDiscovery(massive_client, config.scan.chain_discovery)
matcher = TradeQuoteMatcher(config.scan.aggression_window_seconds)
cluster_builder = ClusterBuilder(config.scan.cluster_window_seconds)
router = AlertRouter(repo, messenger, cooldown, config)

app = FastAPI()


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
async def force_alert(ticker: str):
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker required")
    # simple flow: use discovery to get contracts and process first
    contracts = discovery.contracts_for(ticker)
    if not contracts:
        return JSONResponse({"status": "suppressed", "reason": "no_contracts"})
    option_symbol = contracts[0]
    trades = massive_client.get_option_trades(option_symbol)
    quotes = massive_client.get_option_quotes(option_symbol)
    snapshot = massive_client.get_option_snapshot(option_symbol)
    labeled = matcher.label_aggression(trades, quotes)
    clusters = cluster_builder.build(labeled, snapshot)
    result = router.process_clusters(
        clusters,
        gamma_dte_max=config.scan.gamma_dte_max,
        structural_dte_min=config.scan.structural_dte_min,
    )
    return result


@app.post("/admin/reload-config")
async def reload_config():
    global config
    config = load_config()
    return {"status": "reloaded", "tickers": config.scan.tickers}
