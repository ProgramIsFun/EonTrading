# EonTrading

Trading system: data collection, backtesting, and live execution.

**Scope:** Cash only — no margin, no leverage, no short selling. Max loss = initial capital.

## How it works

News comes in → gets scored for sentiment → triggers trades → broker confirms fill.

```
[news] → [sentiment] → [trade] → [fill]
```

Everything flows through event channels (LocalEventBus or RedisEventBus). See the interactive architecture diagram in the dashboard About tab.

## Quick Start

```bash
# 1. Copy .env.example to .env and fill in your values
cp .env.example .env

# 2. Install (for local dev / API server on host)
pip install -e .

# 3. Start API server on host (manages Docker + serves dashboard)
PYTHONPATH=. uvicorn src.api.server:app --host 0.0.0.0 --port 8000

# 4. Start pipeline in Docker (from dashboard or CLI)
docker compose --profile distributed up -d    # all components + Redis
docker compose up -d redis                    # just Redis (if starting components from dashboard)
```

### Deployment layout

```
Host machine (Mac or Windows):
  ├── FastAPI server (native Python, always running)
  │   ├── Serves dashboard API + backtest
  │   ├── Manages Docker containers via subprocess
  │   └── Connects to Redis via localhost:6379 (REDIS_HOST=localhost)
  │
  └── Docker containers (managed by API or CLI)
      ├── redis        (port 6379, exposed to host)
      ├── watcher      (connects to redis:6379 via Docker DNS)
      ├── analyzer     (connects to redis:6379 via Docker DNS)
      ├── trader       (connects to redis:6379 via Docker DNS)
      └── executor     (connects to redis:6379 via Docker DNS)

Browser (same machine or remote):
  └── Dashboard → http://<host>:8000
      ├── Monitor: heartbeat + real-time ping via Redis
      └── Control: start/stop/restart containers
```

**Important:** The API server's `.env` must have `REDIS_HOST=localhost` (host port mapping).
Docker containers get `REDIS_HOST=redis` automatically from `docker-compose.yml`.

## Architecture

```
Mac (dev machine)  ──────>  Windows PC (192.168.0.38)
  - Code & scripts            - Redis (distributed event bus)
  - Strategy dev               - AiRelay (port 3200)
  - Backtesting
```

**Databases:**
- **MongoDB** (`EonTradingDB`) — all persistent state: news, positions, trades, OHLCV, symbols

### Deployment Modes

| Mode | Command | Event Bus |
|------|---------|-----------|
| Single process (default) | `python -m src.live.news_trader` | LocalEventBus (in-memory) |
| Distributed | Run each runner separately | RedisEventBus (cross-process) |

Distributed runners:
```bash
python -m src.live.runners.run_watcher
python -m src.live.runners.run_analyzer
python -m src.live.runners.run_trader
python -m src.live.runners.run_executor
```

Same component code, both modes. Components don't know which bus they're on.

## Live Trading Pipeline

```
Sources (NewsAPI, Finnhub, RSS, Reddit, Twitter)
  → NewsWatcher (polls via NewsPoller)
    → [news]
      → AnalyzerService (Keyword/LLM + reads positions from MongoDB)
        → [sentiment]
          → SentimentTrader (TradingLogic, tracks pending orders)
            → [trade] ← PriceMonitor (self-managed SL/TP, polls every 60s)
              → Executor → Broker (PaperBroker/Futu/IBKR/Alpaca)
                → [fill] (broker confirms/rejects)
                  → SentimentTrader (persist to MongoDB or rollback)
```

- PriceMonitor checks SL/TP independently — you control risk, not the broker
- MongoDB positions written only after broker confirms fill
- Rejected orders roll back in-memory state
- Pending orders block duplicate trades for the same symbol
- Dedup persisted to MongoDB (`seen_urls` collection) — survives restarts
- Reconciliation on startup: compares system positions vs broker account
- Entry prices persisted to MongoDB — PriceMonitor survives restarts

## Replay Mode (backtest via live pipeline)

Same pipeline code, but fed with historical news and prices:

```bash
# Keyword analyzer, daily SL/TP checks
PRICE_SOURCE=clickhouse PYTHONPATH=. python3 scripts/backtest/live_pipeline_backtest.py

# Pre-scored LLM sentiment, hourly SL/TP checks
PRICE_SOURCE=clickhouse SL_CHECK_HOURS=1 PYTHONPATH=. python3 scripts/backtest/live_pipeline_llm_backtest.py

# Replay from MongoDB news collection
PYTHONPATH=. python3 -m src.live.replay --start 2025-01-01 --end 2025-06-01
```

| Aspect | Live | Replay |
|--------|------|--------|
| News | Real-time from sources | Historical / hardcoded |
| Prices | Latest (yfinance) | Historical (ClickHouse / yfinance) |
| Broker | Real (Futu/IBKR/Alpaca) | PaperBroker (simulated) |
| SL/TP | Background loop (60s) | Stepped through historical timestamps |
| Execution | Distributed (Docker) | Single process |

## Brokers

| Broker | Confirmation | Install | Env vars |
|--------|-------------|---------|----------|
| PaperBroker (default) | Instant (dry run, tracks cash + costs) | — | — |
| Futu | Poll or callback | `pip install futu-api` | `BROKER=futu FUTU_CONFIRM=poll\|callback` |
| Interactive Brokers | Callback via ib_insync | `pip install ib_insync` | `BROKER=ibkr` |
| Alpaca | Polls REST API | `pip install alpaca-trade-api` | `BROKER=alpaca ALPACA_API_KEY ALPACA_SECRET_KEY` |

## News Sources

| Source | Env var | Always on? |
|--------|---------|-----------|
| RSS | — | ✅ |
| Reddit | — | ✅ |
| NewsAPI | `NEWSAPI_KEY` | If key set |
| Finnhub | `FINNHUB_KEY` | If key set |
| Twitter/X | `TWITTER_BEARER_TOKEN` | If key set |

## MongoDB Collections (EonTradingDB)

| Collection | Purpose | Writers | Readers |
|-----------|---------|---------|---------|
| `news` | Articles (live + backfill) | collect_news.py, backfill_news.py | Backtest API |
| `ohlcv` | Price candles | Ingest scripts | Backtest engine |
| `positions` | Open trades with entry timestamps + prices | SentimentTrader (on fill) | AnalyzerService, PriceMonitor |
| `trades` | Confirmed trade history | SentimentTrader (on fill) | API `/api/trades` |
| `replay_positions` | Replay backtest positions (separate from live) | Replay scripts | Replay scripts |
| `replay_trades` | Replay backtest trade log | Replay scripts | — |
| `symbols` | Tracked stock list | update_sp500.py | API, scripts |
| `seen_urls` | Dedup across restarts | NewsPoller | NewsPoller |

## Sentiment Analyzers

| Analyzer | When to use |
|----------|-------------|
| `KeywordSentimentAnalyzer` | Free, fast, no deps |
| `LLMSentimentAnalyzer` | More accurate, needs `OPENAI_API_KEY` or local Ollama |

```python
# Local Ollama
analyzer = LLMSentimentAnalyzer(base_url="http://localhost:11434/v1", model="llama3", api_key="ollama")
```

## Shared: TradingLogic

`src/common/trading_logic.py` — used by both SentimentTrader (live) and Backtest Engine:

`should_buy()`, `should_sell_on_sentiment()`, `check_stop_loss()`, `check_take_profit()`, `update_peak()`

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Status, open positions, component heartbeats |
| `GET /api/ping` | Real-time component status via Redis event bus |
| `GET /api/reconcile` | Compare system positions vs broker account |
| `GET /api/trades` | Confirmed trade history |
| `GET /api/news` | Recent news articles |
| `GET /api/news/count` | Total articles in DB |
| `GET /api/backtest` | Run sentiment backtest (legacy) |
| `GET /api/price-backtest` | Run price-based backtest (SMA/RSI) |
| `POST /api/collector/start` | Start news collector |
| `POST /api/collector/stop` | Stop news collector |
| `GET /api/docker/status` | Docker container states |
| `POST /api/docker/start/{name}` | Start a container |
| `POST /api/docker/stop/{name}` | Stop a container |
| `POST /api/docker/restart/{name}` | Restart a container |
| `GET /api/docker/logs/{name}` | Container logs |

## Testing

```bash
PYTHONPATH=. python -m pytest tests/ -v    # 66 tests, no external deps
```

| Test file | Covers |
|-----------|--------|
| `test_news_trader.py` | Full pipeline, fill confirmation, broker rejection rollback, pending orders, position store |
| `test_position_store.py` | MongoDB position store (mocked) |
| `test_position_aware_analyzer.py` | LLM prompt selection with/without holdings |
| `test_twitter_source.py` | Twitter source (mocked API) |
| `test_backtest.py` | Engine: PnL, drawdown, SL/TP, shorting |
| `test_strategies.py` | SMA crossover, RSI signal generation |
| `test_costs.py` | Transaction cost models |

## Project Structure

```
src/
├── api/server.py                    # FastAPI (backtest + dashboard + trade history)
├── backtest/                        # Backtest engine
├── common/
│   ├── event_bus.py                 # LocalEventBus / RedisEventBus
│   ├── events.py                    # NewsEvent, SentimentEvent, TradeEvent, FillEvent
│   ├── news_poller.py               # Shared polling + persistent dedup
│   ├── position_store.py            # MongoDB-backed position persistence
│   ├── trading_logic.py             # Shared buy/sell logic
│   ├── costs.py                     # Transaction cost models
│   ├── price.py                     # Price lookup (yfinance/ClickHouse + cache)
│   ├── heartbeat.py                 # Component heartbeat to MongoDB
│   ├── ping.py                      # Real-time ping/pong via event bus
│   ├── reconcile.py                 # System vs broker position check
│   ├── startup.py                   # Startup banner + env var status
│   ├── docker_ctl.py                # Docker Compose management via subprocess
│   └── clock.py                     # Simulated clock (replay only)
├── data/
│   ├── news/                        # NewsAPI, Finnhub, RSS, Reddit, Twitter sources
│   ├── providers/                   # yfinance adapter
│   ├── storage/                     # ClickHouse adapter
│   └── utils/db_helper.py           # MongoDB connection
├── live/
│   ├── news_watcher.py              # Polls sources → [news]
│   ├── analyzer_service.py          # [news] → score → [sentiment]
│   ├── sentiment_trader.py          # [sentiment] → decide → [trade], [fill] → persist/rollback
│   ├── price_monitor.py             # Self-managed SL/TP → [trade]
│   ├── news_trader.py               # Single-process entry point
│   ├── replay.py                    # Replay from MongoDB news
│   ├── replay_distributed.py        # Distributed replay via Redis
│   ├── brokers/broker.py            # PaperBroker, FutuBroker, IBKRBroker, AlpacaBroker
│   └── runners/                     # Distributed mode entry points
└── strategies/                      # SMA, RSI, sentiment analyzers
frontend/                            # React + Vite dashboard
scripts/                             # Data collection, backfill, backtest scripts
tests/                               # 66 unit tests
```

## Roadmap

### Done
- [x] Live pipeline: news → sentiment → trade → fill (4-channel event bus)
- [x] 5 news sources: NewsAPI, Finnhub, RSS, Reddit, Twitter
- [x] 4 brokers: PaperBroker, Futu, IBKR, Alpaca
- [x] Fill confirmation: broker confirms → persist, rejects → rollback
- [x] Pending order tracking (no duplicate orders per symbol)
- [x] MongoDB position persistence (survives restarts)
- [x] Trade history logging to MongoDB
- [x] Persistent dedup (seen_urls collection)
- [x] Health check API with position status
- [x] 2 sentiment analyzers: keyword, LLM (position-aware)
- [x] Sentiment + price backtesting with realistic execution
- [x] Risk management: SL/TP, trailing SL, hold limits
- [x] Dashboard: React + Vite + FastAPI
- [x] Architecture diagram in dashboard (About tab)
- [x] Single-process + distributed mode (same code)
- [x] PriceMonitor: self-managed SL/TP (you control risk, not the broker)
- [x] Replay mode: backtest using the live pipeline with historical data
- [x] Pre-scored LLM backtest (simulate LLM output without API calls)
- [x] ClickHouse hourly data for accurate replay SL/TP
- [x] Price cache: Redis (distributed) + in-memory (replay)
- [x] Transaction costs in PaperBroker (US_STOCKS cost model)
- [x] Position reconciliation: system vs broker on startup
- [x] Docker Compose deployment + dashboard container control
- [x] Component heartbeats + real-time ping/pong health check
- [x] Live Redis status indicator in dashboard
- [x] Startup banners with env var status per component
- [x] Entry prices persisted to MongoDB (PriceMonitor survives restarts)
- [x] Separate MongoDB collections for replay vs live positions
- [x] 66 tests passing

### To Do
- [ ] LLM analyzer improvements (context-aware, inverse ETFs)
- [ ] Sector-based trading
- [ ] Backtest with collected real news from MongoDB
- [ ] Compare backtest runs side by side
- [ ] Live dashboard: real-time positions and trade history
- [ ] Telegram/webhook alerts
- [ ] Local LLM via Ollama on Windows PC
