from typing import Dict, List
import httpx
from loguru import logger

from src.config import AppConfig
from src.massive import models
from src.utils.retry import with_retries


class MassiveClient:
    def __init__(self, config: AppConfig):
        self.cfg = config.massive
        self.headers = {"Authorization": f"Bearer {self.cfg.api_key}"} if self.cfg.api_key else {}
        self.client = httpx.Client(base_url=self.cfg.base_url, timeout=self.cfg.timeout)

    @with_retries()
    def get_option_trades(self, option_symbol: str, params: Dict | None = None) -> List[models.OptionTrade]:
        path = self.cfg.trades_path.format(option_symbol=option_symbol)
        response = self.client.get(path, headers=self.headers, params=params or {})
        response.raise_for_status()
        data = response.json()
        try:
            return models.TradesResponse(**data).trades
        except Exception as exc:  # noqa: BLE001
            logger.exception("parse trades failed", error=str(exc), payload=data)
            raise

    @with_retries()
    def get_option_quotes(self, option_symbol: str, params: Dict | None = None) -> List[models.OptionQuote]:
        path = self.cfg.quotes_path.format(option_symbol=option_symbol)
        response = self.client.get(path, headers=self.headers, params=params or {})
        response.raise_for_status()
        data = response.json()
        return models.QuotesResponse(**data).quotes

    @with_retries()
    def get_option_snapshot(self, option_symbol: str) -> models.OptionSnapshot:
        path = self.cfg.snapshot_path.format(option_symbol=option_symbol)
        response = self.client.get(path, headers=self.headers)
        response.raise_for_status()
        data = response.json()
        return models.SnapshotResponse(**data).snapshot

    @with_retries()
    def search_contracts(self, underlying: str, limit: int = 20) -> List[models.OptionContractReference]:
        if not self.cfg.contract_search_path:
            return []
        path = self.cfg.contract_search_path.format(underlying=underlying)
        response = self.client.get(path, headers=self.headers, params={"limit": limit})
        response.raise_for_status()
        data = response.json()
        return models.ContractSearchResponse(**data).contracts
