# EonTrading

**Branch status:** `refactor/sync-to-async` — discarded (tried to refactor too much at once). The `requests` → `httpx` migration is complete on `main`; `pymongo` → `motor` remains pending.

News-driven trading system: data collection, backtesting, and live execution.

**Scope:** Cash only — no margin, no leverage, no short selling. Max loss = initial capital.

## How it works

```
[news] → [sentiment] → [trade] → [fill]
```

Everything flows through event channels (LocalEventBus or RedisStreamBus). See the interactive architecture diagram in the dashboard About tab.

## Quick Start

```bash
# 1. Python 3.11 + venv
python3.11 -m venv .venv && source .venv/bin/activate

# 2. Configure
cp .env.example .env    # edit with your API keys
pip install -e .

# 3. Run
PYTHONPATH=. python -m src.live.news_trader                # single process (default)
PYTHONPATH=. uvicorn src.api.server:app --port 8000        # API + dashboard
```

## Architecture

**Databases:** MongoDB (all state) + Redis (message queue + price cache)

**Deployment:**
- **Single process** — all components in one process via LocalEventBus. Best for dev, replay, debugging.
- **Distributed** — each component in its own container via Redis Streams. Best for production, isolation, scaling.

```bash
python -m src.live.runners.run_watcher
python -m src.live.runners.run_analyzer
python -m src.live.runners.run_trader
python -m src.live.runners.run_executor
```

Same component code, both modes. Components don't know which transport they're on.

## Live Pipeline

```
Sources → NewsWatcher → [news] → AnalyzerService → [sentiment]
  → SentimentTrader → [trade] ← PriceMonitor
    → Executor → Broker → [fill] → SentimentTrader (persist/rollback)
```

- Prices via yfinance (default) or ClickHouse
- SL/TP self-managed by PriceMonitor — same behavior in backtest and live
- MongoDB positions written only after broker confirms fill
- Rejected orders roll back in-memory state
- Reconciliation on startup: system vs broker
- Graceful shutdown on SIGINT/SIGTERM

## Configuration

Copy `.env.example` to `.env`. All vars optional — default is PaperBroker + keyword analyzer, no keys needed.

| Mode | What to set |
|------|-------------|
| Dev (paper + keyword) | Nothing |
| LLM sentiment | `OPENAI_API_KEY` |
| Live broker | `BROKER=`, `ALPACA_API_KEY`, etc. |
| News sources | `NEWSAPI_KEY`, `FINNHUB_KEY`, etc. |

## Brokers

| Broker | Confirmation | Env |
|--------|-------------|-----|
| PaperBroker (default) | Instant (dry run) | — |
| Futu | Poll or callback | `BROKER=futu` + `futu-api` |
| IBKR | Callback | `BROKER=ibkr` + `ib_insync` |
| Alpaca | Poll | `BROKER=alpaca` + keys |

## Replay Mode

Same pipeline, historical data:

```bash
PRICE_SOURCE=clickhouse PYTHONPATH=. python3 scripts/backtest/live_pipeline_keyword_backtest.py
PYTHONPATH=. python3 -m src.live.replay --start 2025-01-01 --end 2025-06-01
```

## Testing

```bash
PYTHONPATH=. python -m pytest tests/ -m "not redis"   # 96 tests, no Redis
PYTHONPATH=. python -m pytest tests/                   # full suite (needs Redis)
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Status, open positions, heartbeats |
| `GET /api/reconcile` | Compare system vs broker |
| `GET /api/trades` | Trade history |
| `GET /api/news` | Recent articles |
| `GET /api/backtest` | Sentiment backtest (legacy) |
| `GET /api/price-backtest` | Price backtest (SMA/RSI) |
| `POST /api/live-backtest` | Start live pipeline backtest |
| `GET /api/live-backtest/{id}` | Poll backtest result |
| `GET/POST /api/docker/*` | Container management |

## Project Structure

```
src/
├── api/server.py              # FastAPI
├── backtest/                  # Engine, portfolio, sentiment
├── common/                    # Event bus, trading logic, costs, price, heartbeat, etc.
├── data/news/                 # NewsAPI, Finnhub, RSS, Reddit, Twitter
├── data/providers/            # yfinance
├── data/storage/              # ClickHouse
├── live/                      # Watcher, analyzer, trader, monitor, brokers, runners
└── strategies/                # SMA, RSI, sentiment (keyword + LLM)
frontend/                      # React + Vite dashboard
scripts/                       # Data collection, backfill, backtest
tests/                         # 101 tests
```

## Sentiment Analyzers

| Analyzer | When |
|----------|------|
| `KeywordSentimentAnalyzer` | Free, fast, no deps |
| `LLMSentimentAnalyzer` | More accurate, needs key |

Supports OpenAI, Azure OpenAI, and local Ollama.

## Roadmap

**Done:** Live pipeline (4 channels), 5 news sources, 4 brokers, fill confirmation with rollback, pending order tracking, MongoDB persistence, dedup, 2 analyzers (keyword + LLM), SL/TP (trailing), backtesting (sentiment + price), React dashboard, single/distributed modes, Redis Streams, PriceMonitor, replay mode, ClickHouse support, price cache, transaction costs, Docker Compose deployment, heartbeats, graceful shutdown, 101 tests.

**To do:** Cross-source dedup, inverse ETF support, sector trading, real-news backtest, side-by-side comparison, live dashboard, Telegram alerts.
