# EonTrading

Trading system: data collection, backtesting, and live execution.

**Scope:** Cash only — no margin, no leverage, no short selling. Max loss = initial capital.

## How it works

News comes in → gets scored for sentiment → triggers trades → broker confirms fill.

```
[news] → [sentiment] → [trade] → [fill]
```

Everything flows through event channels (LocalEventBus or RedisStreamBus). See the interactive architecture diagram in the dashboard About tab.

## Quick Start

```bash
# 1. Set up environment profile
./env.sh dev       # PaperBroker, keyword analyzer, no API keys needed
./env.sh llm       # PaperBroker + LLM analyzer (needs OPENAI_API_KEY)
./env.sh live      # Real broker + LLM (needs broker API keys)

# 2. Install (for local dev / API server on host)
pip install -e .

# 3. Start API server on host (manages Docker + serves dashboard)
PYTHONPATH=. uvicorn src.api.server:app --host 0.0.0.0 --port 8000

# 4. Start pipeline
PYTHONPATH=. python -m src.live.news_trader                # single process
docker compose --profile distributed up -d                  # distributed (Docker)
docker compose up -d redis                                  # just Redis (if starting components from dashboard)
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

**Databases:**
- **MongoDB** (`EonTradingDB`) — all persistent state: news, positions, trades, OHLCV, symbols
- **Redis** — message queue (Streams) for distributed pipeline, pub/sub for ping/pong, price cache

### Deployment Modes

| Mode | Command | Transport |
|------|---------|-----------|
| Single process (default) | `python -m src.live.news_trader` | LocalEventBus (in-memory) |
| Distributed | Run each runner separately | RedisStreamBus (Redis Streams, persistent) |

**When to use which:**
- **Single process** — local dev, replay/backtest (deterministic ordering, simulated clock), debugging (one log stream, breakpoints work)
- **Distributed** — production (isolate failures), scaling (LLM analyzer is CPU-heavy, watcher is I/O-heavy), per-component restarts and memory limits

Same component code, both modes. Components don't know which transport they're on.

Distributed runners:
```bash
python -m src.live.runners.run_watcher
python -m src.live.runners.run_analyzer
python -m src.live.runners.run_trader
python -m src.live.runners.run_executor
```

**Distributed mode uses Redis Streams** (message queue) — messages persist and survive container restarts. Each component has its own consumer group. Ping/pong uses Redis Pub/Sub (broadcast).

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
- Graceful shutdown on SIGINT/SIGTERM in all runners

## Environment Profiles

Switch between configurations without editing `.env` manually:

```bash
./env.sh          # show available profiles
./env.sh dev      # PaperBroker, keyword analyzer
./env.sh llm      # PaperBroker + LLM analyzer
./env.sh live     # Real broker + LLM
```

## Replay Mode (backtest via live pipeline)

Same pipeline code, but fed with historical news and prices:

```bash
# Keyword analyzer, daily SL/TP checks
PRICE_SOURCE=clickhouse PYTHONPATH=. python3 scripts/backtest/live_pipeline_keyword_backtest.py

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

Supports OpenAI, Azure OpenAI, and local Ollama via env vars:

```bash
# OpenAI (default)
OPENAI_API_KEY=sk-...

# Azure OpenAI
OPENAI_API_KEY=your-azure-key
OPENAI_BASE_URL=https://your-resource.openai.azure.com/openai/deployments/your-deployment
OPENAI_API_VERSION=2025-01-01-preview
OPENAI_MODEL=gpt-4.1

# Local Ollama
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_MODEL=llama3
OPENAI_API_KEY=ollama
```

## Shared: TradingLogic

`src/common/trading_logic.py` — used by both SentimentTrader (live) and Backtest Engine:

`should_buy()`, `should_sell_on_sentiment()`, `check_stop_loss()`, `check_take_profit()`, `update_peak()`

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Status, open positions, component heartbeats |
| `GET /api/ping` | Real-time component status via Redis |
| `GET /api/reconcile` | Compare system positions vs broker account |
| `GET /api/trades` | Confirmed trade history |
| `GET /api/news` | Recent news articles |
| `GET /api/news/count` | Total articles in DB |
| `GET /api/backtest` | Run sentiment backtest (legacy) |
| `GET /api/price-backtest` | Run price-based backtest (SMA/RSI) |
| `POST /api/live-backtest` | Start live pipeline backtest (background job) |
| `GET /api/live-backtest/{id}` | Poll backtest progress/result |
| `POST /api/collector/start` | Start news collector |
| `POST /api/collector/stop` | Stop news collector |
| `GET /api/docker/status` | Docker container states |
| `POST /api/docker/start/{name}` | Start a container |
| `POST /api/docker/stop/{name}` | Stop a container |
| `POST /api/docker/restart/{name}` | Restart a container |
| `GET /api/docker/logs/{name}` | Container logs |

## Testing

```bash
PYTHONPATH=. python -m pytest tests/ -v          # 101 tests (needs Redis for 5)
PYTHONPATH=. python -m pytest tests/ -m "not redis"  # 96 tests, no Redis needed
```

| Test file | Tests | Covers |
|-----------|-------|--------|
| `test_news_trader.py` | 17 | Pipeline, fill confirmation, rollback, pending orders, position store |
| `test_integration.py` | 13 | Full pipeline end-to-end, SL/TP, cash tracking, position sizing |
| `test_redis_event_bus.py` | 12 | RedisStreamBus routing, serialization, consumer groups (mocked) |
| `test_redis_live.py` | 5 | Real Redis Streams: persistence, ack, consumer groups |
| `test_backtest.py` | 12 | Engine: PnL, drawdown, SL/TP, shorting |
| `test_api.py` | 5 | API endpoints: health, live backtest job lifecycle, progress |
| `test_position_aware_analyzer.py` | 5 | LLM prompt selection with/without holdings |
| `test_position_store.py` | 6 | MongoDB position store (mocked) |
| `test_twitter_source.py` | 9 | Twitter source (mocked API) |
| `test_strategies.py` | 7 | SMA crossover, RSI signal generation |
| `test_costs.py` | 5 | Transaction cost models |

## Project Structure

```
src/
├── api/server.py                    # FastAPI (backtest + dashboard + trade history)
├── backtest/                        # Backtest engine
├── common/
│   ├── event_bus.py                 # LocalEventBus / RedisStreamBus
│   ├── events.py                    # NewsEvent, SentimentEvent, TradeEvent, FillEvent
│   ├── sample_news.py               # Shared sample news for demo/backtest
│   ├── news_poller.py               # Shared polling + persistent dedup
│   ├── position_store.py            # MongoDB-backed position persistence
│   ├── trading_logic.py             # Shared buy/sell logic
│   ├── costs.py                     # Transaction cost models
│   ├── price.py                     # Price lookup (yfinance/ClickHouse + cache)
│   ├── heartbeat.py                 # Component heartbeat to MongoDB
│   ├── ping.py                      # Real-time ping/pong via pub/sub
│   ├── reconcile.py                 # System vs broker position check
│   ├── startup.py                   # Startup banner + env var status
│   ├── docker_ctl.py                # Docker Compose management via subprocess
│   └── clock.py                     # Simulated clock + utcnow() helper
├── data/
│   ├── news/                        # NewsAPI, Finnhub, RSS, Reddit, Twitter sources
│   ├── providers/                   # yfinance adapter
│   ├── storage/                     # ClickHouse adapter
│   └── utils/db_helper.py           # MongoDB connection (singleton)
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
tests/                               # 101 tests (unit + integration + Redis)
env.sh                               # Environment profile switcher
```

## Roadmap

### Done
- [x] Live pipeline: news → sentiment → trade → fill (4-channel)
- [x] 5 news sources: NewsAPI, Finnhub, RSS, Reddit, Twitter
- [x] 4 brokers: PaperBroker, Futu, IBKR, Alpaca
- [x] Fill confirmation: broker confirms → persist, rejects → rollback
- [x] Pending order tracking (no duplicate orders per symbol)
- [x] MongoDB position persistence (survives restarts)
- [x] Trade history logging to MongoDB
- [x] Persistent dedup (seen_urls collection)
- [x] Health check API with position status
- [x] 2 sentiment analyzers: keyword, LLM (position-aware)
- [x] LLM supports OpenAI, Azure OpenAI, Ollama
- [x] Sentiment + price backtesting with realistic execution
- [x] Risk management: SL/TP, trailing SL, hold limits
- [x] Dashboard: React + Vite + FastAPI
- [x] Architecture diagram in dashboard (About tab)
- [x] Single-process + distributed mode (same code)
- [x] Redis Streams message queue for distributed mode (persistent, at-least-once)
- [x] Redis Pub/Sub for ping/pong health checks (broadcast)
- [x] PriceMonitor: self-managed SL/TP (you control risk, not the broker)
- [x] Replay mode: backtest using the live pipeline with historical data
- [x] Pre-scored LLM backtest (simulate LLM output without API calls)
- [x] ClickHouse hourly data for accurate replay SL/TP
- [x] Price cache: Redis (distributed) + in-memory (replay)
- [x] Transaction costs in PaperBroker (US_STOCKS cost model)
- [x] Position reconciliation: system vs broker on startup
- [x] Docker Compose deployment + dashboard container control (memory limits)
- [x] Component heartbeats + real-time ping/pong health check
- [x] Live Redis status indicator in dashboard
- [x] Startup banners with env var status per component
- [x] Entry prices persisted to MongoDB (PriceMonitor survives restarts)
- [x] Separate MongoDB collections for replay vs live positions
- [x] Graceful shutdown (SIGINT/SIGTERM) in all runners
- [x] Structured logging across all pipeline components
- [x] Environment profiles (./env.sh dev/llm/live)
- [x] 101 tests passing (unit + integration + Redis)

### To Do
- [ ] Cross-source headline dedup (same story from different sources has different URLs — currently only URL-based dedup)
- [ ] LLM analyzer improvements (context-aware, inverse ETFs)
- [ ] Sector-based trading
- [ ] Backtest with collected real news from MongoDB
- [ ] Compare backtest runs side by side
- [ ] Live dashboard: real-time positions and trade history
- [ ] Telegram/webhook alerts
- [ ] Local LLM via Ollama on Windows PC
