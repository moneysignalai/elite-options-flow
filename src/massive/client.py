from typing import Any, Dict, List, Tuple
from urllib.parse import parse_qsl

import httpx

from src.config import AppConfig
from src.massive import models
from src.utils.retry import with_retries
from src.utils.logging import (
    get_logger,
    log_event,
    log_massive_failure,
    log_massive_request,
    log_massive_response,
)


class MassiveClient:
    def __init__(self, config: AppConfig, logger=None):
        self.cfg = config.massive
        self.headers = self._build_headers()
        self.client = httpx.Client(base_url=self.cfg.base_url, timeout=self.cfg.timeout)
        self.logger = logger or get_logger("app")

        if not self.cfg.api_key:
            log_event(self.logger, "config_invalid", missing=["MASSIVE_API_KEY"])
            raise SystemExit(1)

    @staticmethod
    def _elapsed_ms(response: httpx.Response) -> float | None:
        try:
            return response.elapsed.total_seconds() * 1000 if response.elapsed else None
        except RuntimeError:
            return None

    def _build_headers(self) -> Dict[str, str]:
        mode = (self.cfg.headers_mode or "bearer").lower()
        if mode == "x-api-key":
            return {"x-api-key": self.cfg.api_key}
        return {"Authorization": f"Bearer {self.cfg.api_key}"}

    def _response_preview(self, response: httpx.Response | None) -> str | None:
        if response is None:
            return None
        try:
            return (response.text or "")[:300]
        except Exception:  # noqa: BLE001
            return None

    def _json_safe(self, response: httpx.Response) -> Any:
        try:
            return response.json()
        except Exception as exc:  # noqa: BLE001
            log_massive_failure(
                self.logger,
                str(response.request.url),
                params=None,
                exc=exc,
                status_code=response.status_code,
                response_preview=self._response_preview(response),
            )
            return None

    def _build_contract_search_params(self, underlying: str, limit: int) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if self.cfg.contract_search_query:
            formatted = self.cfg.contract_search_query.format(
                underlying=underlying, symbol=underlying, limit=limit
            )
            params.update(dict(parse_qsl(formatted, keep_blank_values=True)))

        params.setdefault(self.cfg.underlying_param_name or "symbol", underlying)
        params.setdefault("limit", limit)
        return params

    @staticmethod
    def _extract_option_symbol(entry: dict) -> str | None:
        if not isinstance(entry, dict):
            return None

        for key in (
            "option_symbol",
            "optionSymbol",
            "ticker",
            "symbol",
            "optionContract",
            "option_contract",
            "optionContractId",
        ):
            val = entry.get(key)
            if isinstance(val, str) and val:
                return val

        details = entry.get("details")
        if isinstance(details, dict):
            for key in ("ticker", "option_symbol", "optionSymbol", "symbol"):
                val = details.get(key)
                if isinstance(val, str) and val:
                    return val

        return None

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

    def _send_request(
        self,
        request: httpx.Request,
        ticker: str | None = None,
        option_contract: str | None = None,
    ) -> httpx.Response | None:
        url = str(request.url)
        params = dict(request.url.params) if request.url.params else None
        log_massive_request(
            self.logger,
            request.method,
            url,
            params=params,
            ticker=ticker,
            option_contract=option_contract,
        )
        try:
            response = self.client.send(request)
        except Exception as exc:  # noqa: BLE001
            status_code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            preview = self._response_preview(exc.response) if isinstance(exc, httpx.HTTPStatusError) else None
            log_massive_failure(
                self.logger,
                url,
                params,
                exc,
                ticker=ticker,
                option_contract=option_contract,
                status_code=status_code,
                response_preview=preview,
            )
            return None

        if response.status_code != 200:
            log_massive_failure(
                self.logger,
                url,
                params,
                exc=None,
                ticker=ticker,
                option_contract=option_contract,
                status_code=response.status_code,
                response_preview=self._response_preview(response),
            )
            return None

        return response

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
        path = self.cfg.contract_search_path.format(underlying=underlying, symbol=underlying)
        params = self._build_contract_search_params(underlying, limit)
        request = self.client.build_request("GET", path, headers=self.headers, params=params)
        url = str(request.url)
        response = self._send_request(request, ticker=underlying)
        if response is None:
            return []

        elapsed_ms = self._elapsed_ms(response)
        content_type = response.headers.get("content-type")

        data = self._json_safe(response)
        if data is None:
            return []
        payload, top_keys, inferred_key = self._extract_contract_candidates(data)
        contracts = self._parse_contract_references(payload)

        if payload is not None and not isinstance(payload, list):
            log_event(self.logger, "schema_mismatch", top_level_keys=top_keys)

        log_massive_response(
            self.logger,
            status_code=response.status_code,
            elapsed_ms=elapsed_ms,
            content_type=content_type,
            top_level_keys=top_keys,
            parsed_count=len(contracts),
        )

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

    @with_retries()
    def get_option_snapshot(self, underlying: str, limit: int | None = None) -> List[str]:
        path = self.cfg.snapshot_path.format(
            ticker=underlying, symbol=underlying, underlying=underlying
        )
        params: Dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit

        request = self.client.build_request("GET", path, headers=self.headers, params=params)
        response = self._send_request(request, ticker=underlying)
        if response is None:
            return []

        elapsed_ms = self._elapsed_ms(response)
        content_type = response.headers.get("content-type")

        data = self._json_safe(response)
        if data is None:
            return []
        payload, top_keys, inferred_key = self._extract_contract_candidates(data)

        if payload is not None and not isinstance(payload, list):
            log_event(self.logger, "schema_mismatch", top_level_keys=top_keys)

        symbols: List[str] = []
        for entry in payload:
            symbol = self._extract_option_symbol(entry)
            if symbol:
                symbols.append(symbol)

        log_massive_response(
            self.logger,
            status_code=response.status_code,
            elapsed_ms=elapsed_ms,
            content_type=content_type,
            top_level_keys=top_keys,
            parsed_count=len(symbols),
        )

        if not symbols:
            log_event(
                self.logger,
                "no_contracts_found",
                ticker=underlying,
                response_keys=top_keys,
                inferred_list_key=inferred_key,
            )
            return []

        return symbols

    def get_options_snapshot(self, underlying: str, limit: int | None = None) -> List[str]:
        return self.get_option_snapshot(underlying, limit)

    @with_retries()
    def get_option_quotes(self, options_ticker: str) -> List[models.OptionQuote]:
        path = self.cfg.quotes_path.format(options_ticker=options_ticker)
        request = self.client.build_request("GET", path, headers=self.headers)
        response = self._send_request(request, ticker=options_ticker)
        if response is None:
            return []

        elapsed_ms = self._elapsed_ms(response)
        content_type = response.headers.get("content-type")

        data = self._json_safe(response)
        if data is None:
            return []
        payload, top_keys, _ = self._extract_contract_candidates(data)
        if payload is not None and not isinstance(payload, list):
            log_event(self.logger, "schema_mismatch", top_level_keys=top_keys)

        quotes: List[models.OptionQuote] = []
        for entry in payload:
            quote = models.OptionSnapshot._parse_last_quote(entry, options_ticker)
            if quote:
                quotes.append(quote)
            else:
                self.logger.warning("quote_parse_failed", invalid_entry=entry)

        log_massive_response(
            self.logger,
            status_code=response.status_code,
            elapsed_ms=elapsed_ms,
            content_type=content_type,
            top_level_keys=top_keys,
            parsed_count=len(quotes),
        )

        return quotes

    @with_retries()
    def get_option_trades(self, options_ticker: str) -> List[models.OptionTrade]:
        if not self.cfg.trades_path:
            log_event(self.logger, "trades_endpoint_unavailable", ticker=options_ticker)
            return []

        path = self.cfg.trades_path.format(options_ticker=options_ticker)
        request = self.client.build_request("GET", path, headers=self.headers)
        response = self._send_request(request, ticker=options_ticker)
        if response is None:
            return []

        elapsed_ms = self._elapsed_ms(response)
        content_type = response.headers.get("content-type")

        data = self._json_safe(response)
        if data is None:
            return []
        payload, top_keys, _ = self._extract_contract_candidates(data)
        if payload is not None and not isinstance(payload, list):
            log_event(self.logger, "schema_mismatch", top_level_keys=top_keys)

        trades: List[models.OptionTrade] = []
        for entry in payload:
            try:
                trades.append(models.OptionTrade.parse_obj(entry))
                continue
            except Exception:
                trade = models.OptionSnapshot._parse_last_trade(
                    entry,
                    option_symbol=options_ticker,
                    underlying=entry.get("underlying") or entry.get("underlying_ticker") or "",
                )
                if trade:
                    trades.append(trade)
                else:
                    self.logger.warning("trade_parse_failed", invalid_entry=entry)

        log_massive_response(
            self.logger,
            status_code=response.status_code,
            elapsed_ms=elapsed_ms,
            content_type=content_type,
            top_level_keys=top_keys,
            parsed_count=len(trades),
        )

        return trades

    @with_retries()
    def get_contract_snapshot(self, underlying: str, option_symbol: str) -> models.OptionSnapshot | None:
        path_template = self.cfg.quotes_path or self.cfg.trades_path
        if not path_template:
            log_event(
                self.logger,
                "trades_endpoint_unavailable",
                ticker=underlying,
                option_contract=option_symbol,
            )
            return None

        path = path_template.format(
            option_symbol=option_symbol,
            underlying=underlying,
            ticker=underlying,
            options_ticker=option_symbol,
        )
        request = self.client.build_request("GET", path, headers=self.headers)
        response = self._send_request(
            request, ticker=underlying, option_contract=option_symbol
        )
        if response is None:
            return None

        elapsed_ms = self._elapsed_ms(response)
        content_type = response.headers.get("content-type")
        data = self._json_safe(response)
        if data is None:
            return None

        payload = data.get("snapshot") or data.get("result") or data.get("data") or data
        if isinstance(payload, list) and payload:
            payload = payload[0]
        if not isinstance(payload, dict):
            top_level_keys = list(data.keys()) if isinstance(data, dict) else None
            log_event(
                self.logger,
                "schema_mismatch",
                top_level_keys=top_level_keys,
                option_contract=option_symbol,
            )
            log_event(
                self.logger,
                "contract_snapshot_empty",
                ticker=underlying,
                option_contract=option_symbol,
                top_level_keys=top_level_keys,
            )
            return None

        snapshot = models.OptionSnapshot.from_snapshot_payload(payload, logger=self.logger)
        if snapshot is None:
            log_event(
                self.logger,
                "contract_snapshot_missing",
                ticker=underlying,
                option_contract=option_symbol,
                top_level_keys=list(payload.keys()),
            )
            return None

        log_massive_response(
            self.logger,
            status_code=response.status_code,
            elapsed_ms=elapsed_ms,
            content_type=content_type,
            top_level_keys=list(data.keys()) if isinstance(data, dict) else None,
            parsed_count=1 if snapshot else 0,
        )

        return snapshot
