from typing import List

from src.massive.client import MassiveClient
from src.utils.logging import log_event


class ContractDiscovery:
    def __init__(self, client: MassiveClient, mode: str, static_contracts: dict[str, List[str]] | None = None):
        self.client = client
        self.mode = mode
        self.static_contracts = static_contracts or {}

    def contracts_for(self, underlying: str) -> List[str]:
        if self.mode == "static":
            return self.static_contracts.get(underlying, [])
        symbols: List[str] = []
        try:
            symbols = self.client.get_option_snapshot(underlying)
        except Exception as exc:  # noqa: BLE001
            log_event(
                self.client.logger,
                "discovery_snapshot_failed",
                ticker=underlying,
                exception_type=type(exc).__name__,
                exception_message=str(exc),
            )

        if not symbols:
            try:
                contracts = self.client.search_contracts(underlying)
                symbols = [c.option_symbol for c in contracts]
            except Exception as exc:  # noqa: BLE001
                log_event(
                    self.client.logger,
                    "discovery_contract_search_failed",
                    ticker=underlying,
                    exception_type=type(exc).__name__,
                    exception_message=str(exc),
                )
                return []

        return symbols
