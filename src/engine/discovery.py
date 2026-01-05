from typing import List

from src.massive.client import MassiveClient


class ContractDiscovery:
    def __init__(self, client: MassiveClient, mode: str, static_contracts: dict[str, List[str]] | None = None):
        self.client = client
        self.mode = mode
        self.static_contracts = static_contracts or {}

    def contracts_for(self, underlying: str) -> List[str]:
        if self.mode == "static":
            return self.static_contracts.get(underlying, [])
        if getattr(self.client.cfg, "use_legacy_contract_search", False):
            return [c.option_symbol for c in self.client.search_contracts(underlying)]
        return self.client.get_options_snapshot(underlying)
