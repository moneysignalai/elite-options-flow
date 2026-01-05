import os
from dataclasses import dataclass
from typing import List
import re
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
    base_url: str | None
    trades_path: str
    quotes_path: str
    snapshot_path: str
    contract_search_path: str | None
    contract_search_query: str | None
    use_legacy_contract_search: bool
    headers_mode: str = "bearer"
    underlying_param_name: str = "symbol"
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
    alert_cooldown_seconds: int
    cooldown_scope: str
    allow_one_alert_per_ticker: bool
    quotes_mode_score_penalty: float
    quotes_mode_notional_cap: float
    quotes_mode_require_min_oi: float


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
        trades_path=os.getenv(
            "MASSIVE_TRADES_PATH",
            os.getenv("MASSIVE_TRADES_PATH_TEMPLATE", ""),
        ),
        quotes_path=os.getenv(
            "MASSIVE_QUOTES_PATH",
            os.getenv("MASSIVE_QUOTES_PATH_TEMPLATE", "/v3/quotes/{options_ticker}"),
        ),
        snapshot_path=os.getenv(
            "MASSIVE_SNAPSHOT_PATH",
            os.getenv("MASSIVE_SNAPSHOT_PATH_TEMPLATE", "/v3/snapshot/options/{underlying}"),
        ),
        contract_search_path=os.getenv(
            "MASSIVE_CONTRACT_SEARCH_PATH",
            os.getenv(
                "MASSIVE_CONTRACT_SEARCH_PATH_TEMPLATE",
                "/v3/reference/options/contracts",
            ),
        ),
        contract_search_query=os.getenv("MASSIVE_CONTRACT_SEARCH_QUERY"),
        use_legacy_contract_search=_bool("MASSIVE_USE_LEGACY_CONTRACT_SEARCH", False),
        headers_mode=os.getenv("MASSIVE_HEADERS_MODE", "bearer"),
        underlying_param_name=os.getenv("MASSIVE_UNDERLYING_PARAM_NAME", "underlying_ticker"),
    )
    cooldown_scope = os.getenv("COOLDOWN_SCOPE", "contract").lower()
    if cooldown_scope == "ticker":
        cooldown_scope = "contract"

    scan = ScanConfig(
        tickers=_list("SCAN_TICKERS"),
        chain_discovery=os.getenv("CHAIN_DISCOVERY", "snapshot"),
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
        alert_cooldown_seconds=_int("ALERT_COOLDOWN_SECONDS", _int("COOLDOWN_MINUTES", 30) * 60),
        cooldown_scope=cooldown_scope,
        allow_one_alert_per_ticker=_bool("ALLOW_ONE_ALERT_PER_TICKER", False),
        quotes_mode_score_penalty=_float("QUOTES_MODE_SCORE_PENALTY", 0.75),
        quotes_mode_notional_cap=_float("QUOTES_MODE_NOTIONAL_CAP", 250000),
        quotes_mode_require_min_oi=_float("QUOTES_MODE_REQUIRE_MIN_OI", 50),
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


def validate_config(config: AppConfig, logger) -> None:
    missing = []
    massive_env = {
        "MASSIVE_API_KEY": config.massive.api_key,
        "MASSIVE_BASE_URL": config.massive.base_url,
    }

    for key, value in massive_env.items():
        if not value:
            missing.append(key)

    if missing:
        from src.utils.logging import log_event

        log_event(logger, "config_invalid", missing=missing)
        raise SystemExit(1)

    ticker_pattern = re.compile(r"^[A-Z]{1,5}$")
    invalid_tickers = [t for t in config.scan.tickers if not ticker_pattern.match(t)]
    suspicious = [t for t in config.scan.tickers if t == "APPL"]
    if invalid_tickers:
        from src.utils.logging import log_event

        log_event(logger, "scan_ticker_invalid", tickers=invalid_tickers)
    if suspicious:
        from src.utils.logging import log_event

        log_event(logger, "scan_ticker_suspicious", tickers=suspicious, hint="did_you_mean_AAPL")

    if config.massive.use_legacy_contract_search and not config.massive.contract_search_path:
        from src.utils.logging import log_event

        log_event(logger, "config_invalid", missing=["MASSIVE_CONTRACT_SEARCH_PATH"])
        raise SystemExit(1)
