import httpx

from src.massive.client import MassiveClient


class StubResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200
        self.elapsed = None
        self.headers: dict[str, str] = {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class StubClient:
    def __init__(self, base_url: str, payload):
        self.base_url = base_url
        self._payload = payload

    def build_request(self, method: str, path: str, headers=None, params=None):
        return httpx.Request(method, f"{self.base_url}{path}", headers=headers, params=params)

    def send(self, request: httpx.Request):
        return StubResponse(self._payload)


def _snapshot_client(mock_app_config, payload):
    client = MassiveClient(mock_app_config)
    client.client = StubClient(mock_app_config.massive.base_url, payload)
    return client


def test_parses_ticker_in_details(mock_app_config):
    payload = {"results": [{"details": {"ticker": "AAPL260116C00200000"}}]}
    client = _snapshot_client(mock_app_config, payload)

    symbols = client.get_options_snapshot("AAPL")

    assert symbols == ["AAPL260116C00200000"]


def test_parses_option_symbol(mock_app_config):
    payload = {"results": [{"option_symbol": "AAPL260116C00200000"}]}
    client = _snapshot_client(mock_app_config, payload)

    symbols = client.get_options_snapshot("AAPL")

    assert symbols == ["AAPL260116C00200000"]


def test_parses_ticker_list(mock_app_config):
    payload = {"data": [{"ticker": "AAPL260116C00200000"}]}
    client = _snapshot_client(mock_app_config, payload)

    symbols = client.get_options_snapshot("AAPL")

    assert symbols == ["AAPL260116C00200000"]


def test_contract_snapshot_parses_trade_and_quote(mock_app_config):
    payload = {
        "snapshot": {
            "option_symbol": "AAPL260116C00200000",
            "underlying": "AAPL",
            "expiry": "2026-01-16",
            "strike": 200,
            "call_put": "C",
            "last_trade": {
                "price": 1.23,
                "size": 50,
                "timestamp": "2024-01-02T15:00:00Z",
            },
            "last_quote": {
                "bid": 1.2,
                "ask": 1.3,
                "timestamp": "2024-01-02T14:59:59Z",
            },
        }
    }
    client = _snapshot_client(mock_app_config, payload)

    snapshot = client.get_contract_snapshot("AAPL", "AAPL260116C00200000")

    assert snapshot.option_symbol == "AAPL260116C00200000"
    assert snapshot.last_trade and snapshot.last_trade.price == 1.23
    assert snapshot.last_quote and snapshot.last_quote.ask == 1.3
