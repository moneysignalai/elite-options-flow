import os
from dataclasses import dataclass
from typing import List
from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _list(name: str, default: str = "") -> List[str]:
    value = os.getenv(name, default)
    return [item.strip().upper() for item in value.split(",") if item.strip()]


@dataclass
class MassiveConfig:
    api_key: str
    base_url: str
    trades_path: str
    quotes_path: str
    snapshot_path: str
    contract_search_path: str | None
    timeout: float = 10.0


@dataclass
class ScanConfig:
    tickers: List[str]
    chain_discovery: str
    enable_premarket: bool
    enable_afterhours: bool
    scan_interval_seconds: int
    rth_start: str
    rth_end: str
    aggression_window_seconds: int
    cluster_window_seconds: int
    max_lookback_minutes: int
    gamma_dte_max: int
    structural_dte_min: int
    alert_score_threshold: float
    deep_dive_threshold: float
    medium_threshold: float
    cooldown_minutes: int


@dataclass
class TelegramConfig:
    bot_token: str | None
    chat_id: str | None


@dataclass
class AppConfig:
    massive: MassiveConfig
    scan: ScanConfig
    telegram: TelegramConfig
    database_url: str | None
    enable_postgres: bool



def load_config() -> AppConfig:
    massive = MassiveConfig(
        api_key=os.getenv("MASSIVE_API_KEY", ""),
        base_url=os.getenv("MASSIVE_BASE_URL", "https://api.massive.com"),
        trades_path=os.getenv("MASSIVE_TRADES_PATH_TEMPLATE", "/options/trades?symbol={option_symbol}"),
        quotes_path=os.getenv("MASSIVE_QUOTES_PATH_TEMPLATE", "/options/quotes?symbol={option_symbol}"),
        snapshot_path=os.getenv("MASSIVE_SNAPSHOT_PATH_TEMPLATE", "/options/snapshot?symbol={option_symbol}"),
        contract_search_path=os.getenv("MASSIVE_CONTRACT_SEARCH_PATH"),
    )
    scan = ScanConfig(
        tickers=_list("SCAN_TICKERS"),
        chain_discovery=os.getenv("CHAIN_DISCOVERY", "reference"),
        enable_premarket=_bool("ENABLE_PREMARKET", False),
        enable_afterhours=_bool("ENABLE_AFTERHOURS", False),
        scan_interval_seconds=_int("SCAN_INTERVAL_SECONDS", 30),
        rth_start=os.getenv("RTH_START", "09:30"),
        rth_end=os.getenv("RTH_END", "16:00"),
        aggression_window_seconds=_int("AGGRESSION_WINDOW_SECONDS", 120),
        cluster_window_seconds=_int("CLUSTER_WINDOW_SECONDS", 90),
        max_lookback_minutes=_int("MAX_LOOKBACK_MINUTES", 5),
        gamma_dte_max=_int("GAMMA_DTE_MAX", 3),
        structural_dte_min=_int("STRUCTURAL_DTE_MIN", 30),
        alert_score_threshold=_float("ALERT_SCORE_THRESHOLD", 6.0),
        deep_dive_threshold=_float("DEEP_DIVE_THRESHOLD", 9.0),
        medium_threshold=_float("MEDIUM_THRESHOLD", 7.0),
        cooldown_minutes=_int("COOLDOWN_MINUTES", 30),
    )
    telegram = TelegramConfig(
        bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
        chat_id=os.getenv("TELEGRAM_CHAT_ID"),
    )
    database_url = os.getenv("DATABASE_URL")
    return AppConfig(
        massive=massive,
        scan=scan,
        telegram=telegram,
        database_url=database_url if database_url else None,
        enable_postgres=_bool("ENABLE_POSTGRES", False),
    )
