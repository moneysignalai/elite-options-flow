from __future__ import annotations

from datetime import date
import re
from typing import TypedDict


class OpraFields(TypedDict):
    root: str
    expiry: date
    strike: float
    call_put: str


_OPRA_RE = re.compile(r"^O:(?P<root>[A-Z]{1,6})(?P<yy>\d{2})(?P<mm>\d{2})(?P<dd>\d{2})(?P<cp>[CP])(?P<strike>\d{8})$")


def parse_opra_symbol(symbol: str) -> OpraFields | None:
    match = _OPRA_RE.match(symbol or "")
    if not match:
        return None

    groups = match.groupdict()
    year = 2000 + int(groups["yy"])
    month = int(groups["mm"])
    day = int(groups["dd"])
    try:
        expiry = date(year, month, day)
    except ValueError:
        return None

    strike_raw = int(groups["strike"])
    strike = strike_raw / 1000.0

    return {
        "root": groups["root"],
        "expiry": expiry,
        "strike": strike,
        "call_put": groups["cp"],
    }
