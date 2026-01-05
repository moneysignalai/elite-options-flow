#!/usr/bin/env python
import sys

from src.config import load_config, validate_config
from src.massive.client import MassiveClient
from src.utils.logging import get_logger, log_event


def main() -> int:
    logger = get_logger("massive_smoke_test")
    config = load_config()
    validate_config(config, logger)

    client = MassiveClient(config, logger=logger)
    ticker = "SPY"
    try:
        contracts = client.search_contracts(ticker)
    except Exception as exc:  # noqa: BLE001
        log_event(
            logger,
            "contract_search_failed",
            ticker=ticker,
            exception_type=type(exc).__name__,
            exception_message=str(exc),
        )
        print(f"massive_smoke_test status=error message={exc}")
        return 2

    count = len(contracts)
    print(f"massive_smoke_test status=ok count={count}")
    return 0 if count > 0 else 2


if __name__ == "__main__":
    sys.exit(main())
