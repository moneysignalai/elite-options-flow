from datetime import date

import pytest

from src.massive.client import MassiveClient


@pytest.fixture
def client(mock_app_config):
    # Logger not required for parsing-only tests
    return MassiveClient(mock_app_config)


def _sample_contract(symbol: str) -> dict:
    return {
        "option_symbol": symbol,
        "expiry": "2024-01-19",
        "strike": 200,
        "call_put": "call",
    }


def test_extracts_from_results_key(client):
    payload = {"results": [_sample_contract("TSLA240119C00200000")]}
    candidates, top_keys, inferred = client._extract_contract_candidates(payload)

    assert inferred == "results"
    assert top_keys == ["results"]
    contracts = client._parse_contract_references(candidates)
    assert len(contracts) == 1
    assert contracts[0].option_symbol == "TSLA240119C00200000"
    assert isinstance(contracts[0].expiry, date)


def test_extracts_from_data_key(client):
    payload = {"data": [_sample_contract("AAPL240119C00200000")]}   # type: ignore[list-item]
    candidates, top_keys, inferred = client._extract_contract_candidates(payload)

    assert inferred == "data"
    assert set(top_keys) == {"data"}
    contracts = client._parse_contract_references(candidates)
    assert len(contracts) == 1
    assert contracts[0].option_symbol == "AAPL240119C00200000"


def test_extracts_from_top_level_list(client):
    payload = [_sample_contract("MSFT240119C00200000"), _sample_contract("MSFT240119P00200000")]
    candidates, top_keys, inferred = client._extract_contract_candidates(payload)

    assert inferred is None
    assert top_keys == []
    contracts = client._parse_contract_references(candidates)
    assert len(contracts) == 2
    assert {c.option_symbol for c in contracts} == {"MSFT240119C00200000", "MSFT240119P00200000"}
