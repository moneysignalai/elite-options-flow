import httpx
from httpx import Response

from src.massive.client import MassiveClient


def _client_with_transport(config, responder):
    client = MassiveClient(config)
    client.client = httpx.Client(
        base_url=config.massive.base_url,
        transport=httpx.MockTransport(responder),
    )
    return client


def test_contract_search_url(mock_app_config):
    captured = {}

    def responder(request: httpx.Request) -> Response:
        captured["path"] = request.url.path
        captured["params"] = dict(request.url.params)
        payload = {
            "contracts": [
                {
                    "option_symbol": "AAPL240621C00100000",
                    "expiry": "2024-06-21",
                    "strike": 100,
                    "call_put": "C",
                }
            ]
        }
        return Response(200, json=payload)

    client = _client_with_transport(mock_app_config, responder)
    contracts = client.search_contracts("AAPL")

    assert captured["path"] == "/v3/reference/options/contracts"
    assert captured["params"].get("symbol") == "AAPL"
    assert captured["params"].get("limit") == "20"
    assert contracts and contracts[0].option_symbol == "AAPL240621C00100000"


def test_snapshot_url(mock_app_config):
    captured = {}

    def responder(request: httpx.Request) -> Response:
        captured["path"] = request.url.path
        payload = {"data": [{"option_symbol": "AAPL240621C00100000"}]}
        return Response(200, json=payload)

    client = _client_with_transport(mock_app_config, responder)
    symbols = client.get_option_snapshot("AAPL")

    assert captured["path"] == "/v3/snapshot/options/AAPL"
    assert symbols == ["AAPL240621C00100000"]


def test_quotes_url(mock_app_config):
    captured = {}

    def responder(request: httpx.Request) -> Response:
        captured["path"] = request.url.path
        payload = {
            "data": [
                {
                    "option_symbol": "AAPL240621C00100000",
                    "bid": 1.0,
                    "ask": 1.2,
                    "timestamp": "2024-01-01T00:00:00Z",
                }
            ]
        }
        return Response(200, json=payload)

    client = _client_with_transport(mock_app_config, responder)
    quotes = client.get_option_quotes("AAPL240621C00100000")

    assert captured["path"] == "/v3/quotes/AAPL240621C00100000"
    assert quotes and quotes[0].bid == 1.0
