from datetime import datetime, date
from pydantic import BaseModel
from typing import List, Optional


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
