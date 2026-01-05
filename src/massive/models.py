from datetime import datetime, date
from typing import List, Optional

from pydantic import BaseModel

from src.massive.opra import parse_opra_symbol
from src.utils.logging import get_logger, log_event
from src.massive.timestamp import normalize_timestamp_to_datetime


class OptionTrade(BaseModel):
    option_symbol: str
    underlying: str
    trade_time: datetime
    price: float
    size: float
    side: Optional[str] = None  # unknown, we infer using quotes


class OptionQuote(BaseModel):
    option_symbol: str
    bid: float
    ask: float
    bid_size: int = 0
    ask_size: int = 0
    exchange: Optional[int] = None
    quote_time: datetime


class OptionSnapshot(BaseModel):
    option_symbol: str
    underlying: str
    expiry: date
    strike: float
    call_put: str
    oi: Optional[float]
    iv: Optional[float]
    delta: Optional[float]
    gamma: Optional[float]
    underlying_price: Optional[float]
    day_volume: Optional[float] = None
    day_notional: Optional[float] = None
    day_vwap: Optional[float] = None
    last_trade: Optional[OptionTrade] = None
    last_quote: Optional[OptionQuote] = None

    @staticmethod
    def _parse_last_trade(data: dict, option_symbol: str, underlying: str) -> OptionTrade | None:
        if not isinstance(data, dict):
            return None
        price = data.get("price") or data.get("last_price")
        size = data.get("size") or data.get("quantity") or data.get("volume")
        trade_time = data.get("timestamp") or data.get("time") or data.get("trade_time")
        if price is None or size is None or trade_time is None:
            return None
        return OptionTrade(
            option_symbol=option_symbol,
            underlying=underlying,
            trade_time=trade_time,
            price=float(price),
            size=float(size),
            side=data.get("side"),
        )

    @staticmethod
    def _parse_last_quote(
        data: dict, option_symbol: str
    ) -> tuple[OptionQuote | None, str | None]:
        if not isinstance(data, dict):
            return None, "non_dict"

        bid = data.get("bid") or data.get("bid_price")
        ask = data.get("ask") or data.get("ask_price")
        bid_size = data.get("bid_size") or data.get("bidSize")
        ask_size = data.get("ask_size") or data.get("askSize")
        exchange = data.get("exchange") or data.get("exch")
        raw_timestamp = (
            data.get("sip_timestamp")
            or data.get("timestamp")
            or data.get("time")
            or data.get("quote_time")
        )

        if bid is None or ask is None or raw_timestamp is None:
            return None, "missing_fields"

        ts_dt = normalize_timestamp_to_datetime(raw_timestamp)
        quote_time = ts_dt or raw_timestamp

        try:
            return (
                OptionQuote(
                    option_symbol=option_symbol,
                    bid=float(bid),
                    ask=float(ask),
                    bid_size=int(bid_size) if bid_size is not None else 0,
                    ask_size=int(ask_size) if ask_size is not None else 0,
                    exchange=int(exchange) if exchange is not None else None,
                    quote_time=quote_time,
                ),
                None,
            )
        except OverflowError:
            return None, "timestamp_out_of_range"
        except Exception:  # noqa: BLE001
            return None, "type_error"

    @classmethod
    def from_quotes_payload(cls, payload: dict, option_symbol: str, logger=None) -> "OptionSnapshot | None":
        log = logger or get_logger("app")

        if not isinstance(payload, dict):
            log_event(log, "contract_snapshot_missing", option_symbol=option_symbol, reason="non_dict")
            return None

        parsed_symbol = parse_opra_symbol(option_symbol) if option_symbol else None
        if not parsed_symbol:
            log_event(log, "opra_parse_failed", option_symbol=option_symbol)
            return None

        underlying = (
            payload.get("underlying")
            or payload.get("underlying_symbol")
            or payload.get("underlying_ticker")
            or parsed_symbol.get("root", "")
        )
        expiry = payload.get("expiry") or payload.get("expiration") or payload.get("expiration_date")
        strike = payload.get("strike") or payload.get("strike_price")
        call_put = payload.get("call_put") or payload.get("type") or payload.get("option_type")

        expiry = expiry or parsed_symbol.get("expiry")
        strike = strike or parsed_symbol.get("strike")
        call_put = (call_put or parsed_symbol.get("call_put") or "").upper()[:1]

        iv = payload.get("iv") or payload.get("implied_volatility")
        delta = payload.get("delta")
        gamma = payload.get("gamma")
        underlying_price = payload.get("underlying_price") or payload.get("underlyingPrice")
        day = payload.get("day") or {}
        day_volume = day.get("volume") if isinstance(day, dict) else payload.get("volume")
        day_notional = day.get("notional") if isinstance(day, dict) else payload.get("notional")
        day_vwap = day.get("vwap") if isinstance(day, dict) else payload.get("vwap")

        missing_fields = [name for name, value in (("expiry", expiry), ("strike", strike)) if value is None]
        if missing_fields:
            log_event(
                log,
                "contract_snapshot_missing_fields",
                option_symbol=option_symbol,
                missing_fields=missing_fields,
                top_level_keys=list(payload.keys()),
            )
            log_event(
                log,
                "massive_quote_missing_fields",
                option_symbol=option_symbol,
                reason="missing_fields",
            )
            return None

        last_quote, _ = cls._parse_last_quote(payload, option_symbol)
        last_trade = cls._parse_last_trade(payload, option_symbol, underlying)

        try:
            return cls(
                option_symbol=option_symbol,
                underlying=underlying,
                expiry=expiry,
                strike=strike,
                call_put=call_put,
                oi=payload.get("oi") or payload.get("open_interest"),
                iv=iv,
                delta=delta,
                gamma=gamma,
                underlying_price=underlying_price,
                day_volume=day_volume,
                day_notional=day_notional,
                day_vwap=day_vwap,
                last_trade=last_trade,
                last_quote=last_quote,
            )
        except Exception as exc:  # noqa: BLE001
            log_event(
                log,
                "contract_snapshot_invalid",
                option_symbol=option_symbol,
                exception_type=type(exc).__name__,
                exception_message=str(exc),
            )
            return None

    @classmethod
    def from_snapshot_payload(cls, payload: dict, logger=None) -> "OptionSnapshot | None":
        log = logger or get_logger("app")
        option_symbol = (
            payload.get("option_symbol")
            or payload.get("optionSymbol")
            or payload.get("optionContract")
            or payload.get("option_contract")
            or payload.get("ticker")
            or ""
        )
        underlying = (
            payload.get("underlying")
            or payload.get("underlying_symbol")
            or payload.get("underlying_ticker")
            or payload.get("underlyingAsset")
            or payload.get("ticker_root")
            or ""
        )
        parsed_symbol = parse_opra_symbol(option_symbol) if option_symbol else None
        if not parsed_symbol and option_symbol:
            log_event(log, "opra_parse_failed", option_symbol=option_symbol)

        expiry = payload.get("expiry") or payload.get("expiration") or payload.get("expiration_date")
        strike = payload.get("strike") or payload.get("strike_price")
        call_put = payload.get("call_put") or payload.get("type") or payload.get("option_type")

        if parsed_symbol:
            expiry = expiry or parsed_symbol["expiry"]
            strike = strike or parsed_symbol["strike"]
            call_put = call_put or parsed_symbol["call_put"]
        oi = payload.get("oi") or payload.get("open_interest")
        iv = payload.get("iv") or payload.get("implied_volatility")
        delta = payload.get("delta")
        gamma = payload.get("gamma")
        underlying_price = payload.get("underlying_price") or payload.get("underlyingPrice")
        day = payload.get("day") or {}
        day_volume = day.get("volume") if isinstance(day, dict) else payload.get("volume")
        day_notional = day.get("notional") if isinstance(day, dict) else payload.get("notional")
        day_vwap = day.get("vwap") if isinstance(day, dict) else payload.get("vwap")

        missing_fields = [name for name, value in (("expiry", expiry), ("strike", strike)) if value is None]
        if missing_fields:
            log_event(
                log,
                "contract_snapshot_missing_fields",
                option_symbol=option_symbol,
                missing_fields=missing_fields,
                top_level_keys=list(payload.keys()),
            )
            log_event(
                log,
                "massive_quote_missing_fields",
                option_symbol=option_symbol,
                reason="missing_fields",
            )
            return None

        normalized = {
            "option_symbol": option_symbol,
            "underlying": underlying,
            "expiry": expiry,
            "strike": strike,
            "call_put": (call_put or "").upper()[:1],
            "oi": oi,
            "iv": iv,
            "delta": delta,
            "gamma": gamma,
            "underlying_price": underlying_price,
            "day_volume": day_volume,
            "day_notional": day_notional,
            "day_vwap": day_vwap,
        }

        last_trade = cls._parse_last_trade(payload.get("last_trade"), option_symbol, underlying)
        last_quote, reason = cls._parse_last_quote(payload.get("last_quote"), option_symbol)
        if reason:
            log_event(log, "massive_quote_missing_fields", option_symbol=option_symbol, reason=reason)

        try:
            return cls(**normalized, last_trade=last_trade, last_quote=last_quote)
        except Exception as exc:  # noqa: BLE001
            log_event(
                log,
                "contract_snapshot_invalid",
                option_symbol=option_symbol,
                exception_type=type(exc).__name__,
                exception_message=str(exc),
            )
            return None


class OptionContractReference(BaseModel):
    option_symbol: str
    expiry: date
    strike: float
    call_put: str


class TradesResponse(BaseModel):
    trades: List[OptionTrade]


class QuotesResponse(BaseModel):
    quotes: List[OptionQuote]


class SnapshotResponse(BaseModel):
    snapshot: OptionSnapshot


class ContractSearchResponse(BaseModel):
    contracts: List[OptionContractReference]
