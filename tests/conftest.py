import sys, os

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.config import AppConfig, MassiveConfig, ScanConfig, TelegramConfig


@pytest.fixture
def mock_app_config() -> AppConfig:
    return AppConfig(
        massive=MassiveConfig(
            api_key="test",
            base_url="https://api.massive.test",
            trades_path="",
            quotes_path="/v3/quotes/{options_ticker}",
            snapshot_path="/v3/snapshot/options/{underlying}",
            contract_search_path="/v3/reference/options/contracts",
            contract_search_query=None,
            use_legacy_contract_search=False,
            headers_mode="bearer",
            underlying_param_name="symbol",
            timeout=5.0,
        ),
        scan=ScanConfig(
            tickers=[],
            chain_discovery="reference",
            enable_premarket=False,
            enable_afterhours=False,
            scan_interval_seconds=30,
            rth_start="09:30",
            rth_end="16:00",
            aggression_window_seconds=120,
            cluster_window_seconds=90,
            max_lookback_minutes=5,
            gamma_dte_max=3,
            structural_dte_min=30,
            alert_score_threshold=6.0,
            deep_dive_threshold=9.0,
            medium_threshold=7.0,
            cooldown_minutes=30,
            alert_cooldown_seconds=30 * 60,
            cooldown_scope="contract",
            allow_one_alert_per_ticker=False,
            quotes_mode_score_penalty=0.75,
            quotes_mode_notional_cap=250000,
            quotes_mode_require_min_oi=50,
        ),
        telegram=TelegramConfig(bot_token=None, chat_id=None),
        database_url=None,
        enable_postgres=False,
    )
