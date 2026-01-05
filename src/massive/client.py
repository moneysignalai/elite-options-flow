from typing import Any, Dict, List, Tuple
import httpx

from src.config import AppConfig
from src.massive import models
from src.utils.retry import with_retries
from src.utils.logging import get_logger, log_event


class MassiveClient:
    def __init__(self, config: AppConfig, logger=None):
        self.cfg = config.massive
        self.headers = {"Authorization": f"Bearer {self.cfg.api_key}"} if self.cfg.api_key else {}
        self.client = httpx.Client(base_url=self.cfg.base_url, timeout=self.cfg.timeout)
        self.logger = logger or get_logger("app")

    @with_retries()
    def get_option_trades(self, option_symbol: str, params: Dict | None = None) -> List[models.OptionTrade]:
        path = self.cfg.trades_path.format(option_symbol=option_symbol)
        response = self.client.get(path, headers=self.headers, params=params or {})
        response.raise_for_status()
        data = response.json()
        try:
            return models.TradesResponse(**data).trades
        except Exception as exc:  # noqa: BLE001
            self.logger.exception(
                "parse trades failed",
                where="MassiveClient.get_option_trades",
                exception_type=type(exc).__name__,
                exception_message=str(exc),
                payload_size=len(str(data)),
            )
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

    @staticmethod
    def _extract_contract_candidates(data: Any) -> Tuple[List[dict], List[str], str | None]:
        """Return potential contract list, top-level keys, and the inferred list key if any."""

        top_level_keys: List[str] = []
        if isinstance(data, dict):
            top_level_keys = list(data.keys())
            for key in ("results", "data", "contracts", "options"):
                if key in data:
                    payload = data.get(key) or []
                    return payload if isinstance(payload, list) else [], top_level_keys, key
            return [], top_level_keys, None

        if isinstance(data, list):
            return data, top_level_keys, None

        return [], top_level_keys, None

    def _parse_contract_references(self, payload: List[dict]) -> List[models.OptionContractReference]:
        contracts: List[models.OptionContractReference] = []
        for entry in payload:
            try:
                contracts.append(models.OptionContractReference.parse_obj(entry))
            except Exception:  # noqa: BLE001
                self.logger.warning("contract_search_parse_contract_failed", invalid_entry=entry)
        return contracts

    @with_retries()
    def search_contracts(self, underlying: str, limit: int = 20) -> List[models.OptionContractReference]:
        if not self.cfg.contract_search_path:
            return []
        path = self.cfg.contract_search_path.format(underlying=underlying)
        params = {"limit": limit}
        response = self.client.get(path, headers=self.headers, params=params)
        url = str(response.request.url)
        log_event(self.logger, "contract_search_request", ticker=underlying, url=url, params=params)

        response.raise_for_status()
        elapsed_ms = response.elapsed.total_seconds() * 1000 if response.elapsed else None
        content_type = response.headers.get("content-type")

        data = response.json()
        payload, top_keys, inferred_key = self._extract_contract_candidates(data)
        item_count_guess = len(payload)

        log_event(
            self.logger,
            "contract_search_response",
            status_code=response.status_code,
            elapsed_ms=elapsed_ms,
            content_type=content_type,
            top_level_keys=top_keys,
            item_count_guess=item_count_guess,
        )

        contracts = self._parse_contract_references(payload)

        if not contracts:
            preview = (response.text or "")[:300]
            log_event(
                self.logger,
                "contract_search_empty",
                url=url,
                params=params,
                status_code=response.status_code,
                response_preview=preview,
                parsed_top_keys=top_keys,
                inferred_list_key=inferred_key,
            )

        return contracts
