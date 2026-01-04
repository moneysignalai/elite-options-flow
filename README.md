# Elite Options Flow Intelligence Engine (v1)

Production-ready Render blueprint for options flow intelligence built on Massive.com Options API (trades + quotes + snapshot). Architecture is modular so earnings/news can be added later.

## Features
- Continuous scanner worker plus FastAPI web service for status/health.
- Massive Options API adapter with configurable endpoint templates (trades, quotes, snapshot, optional contract search).
- Cluster builder aggregates prints into 90s windows and computes premium, aggression, sweep density, OI context.
- Aggression inference by matching trades to nearest quotes.
- Setup classifier (GAMMA_EXPANSION, STRUCTURAL_BUILD, INFORMATIONAL, HEDGE_SUPPRESS, PINNING placeholder).
- Scoring engine (0–10) with explainable components and tags.
- Dedupe + cooldown with score/premium bump overrides.
- Alert templating (SHORT, MEDIUM, DEEP_DIVE) auto-selected by score.
- Telegram messaging with graceful disable when env missing.
- Optional Postgres persistence via SQLAlchemy + Alembic; in-memory fallback when DATABASE_URL unset.
- Render-friendly structured logs.

## Repository Layout
```
render.yaml
Dockerfile
requirements.txt
.env.example
start_web.sh
start_worker.sh
alembic/
  env.py
  versions/0001_create_alerts.py
src/
  main_web.py
  worker.py
  config.py
  logging_setup.py
  massive/
    client.py
    models.py
  engine/
    discovery.py
    ingest.py
    cluster.py
    classify.py
    score.py
    dedupe.py
    templates.py
    alert_router.py
  messaging/
    telegram.py
  storage/
    db.py
    models.py
    repository.py
  utils/
    time.py
    retry.py
tests/
  fixtures/sample_trades.json
  fixtures/sample_quotes.json
  test_cluster.py
  test_score.py
  test_dedupe.py
```

## Massive API endpoints
Update the templates in `.env.example` with the correct paths for your Massive account:
- `MASSIVE_TRADES_PATH_TEMPLATE`
- `MASSIVE_QUOTES_PATH_TEMPLATE`
- `MASSIVE_SNAPSHOT_PATH_TEMPLATE`
- `MASSIVE_CONTRACT_SEARCH_PATH` (optional, used when `CHAIN_DISCOVERY=reference`)
Only Massive Options API endpoints are called in v1.

## Environment Variables
Copy `.env.example` to `.env` and fill in:
- `MASSIVE_API_KEY`
- `MASSIVE_BASE_URL`
- `SCAN_TICKERS` (comma list of underlyings)
- `CHAIN_DISCOVERY` (`reference` or `static`)
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (optional)
- `DATABASE_URL` (optional Postgres connection string)
- Additional tunables: window sizes, thresholds, market hours, cooldown.

## Contract Discovery Modes
- `CHAIN_DISCOVERY=reference` (default): uses Massive contract search endpoint to grab nearby contracts per underlying.
- `CHAIN_DISCOVERY=static`: provide a JSON mapping in code or env (extend `ContractDiscovery` initialization) with explicit option symbols per underlying.

## Running Locally
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export $(cat .env | xargs)  # or set manually
python start_web.sh  # FastAPI on :8000
python start_worker.sh  # scanner loop
```

## Deploy to Render
1. Push this repo to your Git provider.
2. On Render, create a new Blueprint and point to `render.yaml`.
3. Supply environment variables for both services (web + worker). DATABASE_URL is optional; if omitted, in-memory storage is used.
4. Deploy. Web service health check is `/health`.

## Database (optional)
- If `DATABASE_URL` is set, SQLAlchemy will persist alerts and dedupe state. Run Alembic migration locally or via a one-off job:
  ```bash
  DATABASE_URL=... alembic upgrade head
  ```
- If not set, alerts are stored in-memory (bounded deque) and dedupe uses local cache.

## API Endpoints
- `GET /health`
- `GET /status`
- `GET /alerts/recent?limit=100`
- `POST /debug/force-alert?ticker=SPY` (runs immediate scan for ticker)
- `POST /admin/reload-config`

## Logging
Examples (Render-friendly key/value):
- `scan start | universe_count=...`
- `ticker start | ticker=...`
- `cluster build | candidates=... clusters=...`
- `alert sent | id=... score=... setup=...`
- `alert suppressed | reason=dedupe|below_threshold`
- `scan end | duration_ms=... triggered=... suppressed=... errors=...`

## Alert Examples
- SHORT: `score 6.2` aggressive sweep, near-dated OTM.
- MEDIUM: `score 7.5` strong aggression + premium size.
- DEEP_DIVE: `score 9.3` large structural build with clean aggression + vol/oi stretch.

## Testing
```bash
pytest
```

## Notes
- Market window defaults to US RTH (America/New_York). Premarket/afterhours toggles available.
- Messaging fails gracefully when Telegram env vars are missing.
- Massive endpoint templates may need adjustment for your plan; update `.env` accordingly before deploying.
