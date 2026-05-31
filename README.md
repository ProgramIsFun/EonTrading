# EonTrading

News-driven trading system: data collection, backtesting, and live execution.

**Scope:** Cash only — no margin, no leverage, no short selling. Max loss = initial capital.

## How it works

```
[news] → [sentiment] → [trade]
```

Everything flows through event channels (LocalEventBus or RedisStreamBus). Fill confirmation is handled by OrderTracker (polls `orders` collection), not a channel. See the interactive architecture diagram in the dashboard About tab.

## Quick Start

```bash
# 1. Python 3.11 + venv
python3.11 -m venv .venv && source .venv/bin/activate

# 2. Configure
cp .env.example .env    # edit with your API keys
pip install -e .

# 3. Run
PYTHONPATH=. python -m src.live.news_trader                # single process (default)
./scripts/start_distributed.sh start                       # distributed — all 7 components
./scripts/start_distributed.sh stop                        # stop all
./scripts/start_distributed.sh status                      # check running processes
```

## Architecture

**Databases:** MongoDB (all state) + Redis (message queue + price cache)

**Deployment:**
- **Single process** — all components in one process via LocalEventBus. Best for dev, replay, debugging.
- **Distributed** — each component in its own process via Redis Streams. Best for production, isolation, scaling.

```bash
python -m src.live.runners.run_watcher          # news → [news]
python -m src.live.runners.run_analyzer         # [news] → [sentiment]
python -m src.live.runners.run_trader           # [sentiment] → [trade]
python -m src.live.runners.run_executor          # [trade] → orders (MongoDB)
python -m src.live.runners.run_monitor          # monitors SL/TP → [trade]
python -m src.live.runners.run_order_tracker     # orders → positions on fill
uvicorn src.api.server:app --port 8000           # REST API + dashboard
```

Or use `./scripts/start_distributed.sh start` to run all 7 at once.

Same component code, all modes. Components don't know which transport they're on.

## Live Pipeline

```
Sources → NewsWatcher → [news] → AnalyzerService → [sentiment]
  → SentimentTrader → [trade] ← PriceMonitor
    → TradeExecutor → orders (MongoDB) ← OrderTracker (polls) → PositionStore
```

- SL/TP self-managed by PriceMonitor — same behavior in backtest and live
- OrderTracker is the sole handler of fill confirmation — polls `orders`, updates `positions` on fill
- TradeExecutor only submits trades to broker and writes to `orders` — never touches positions
- PositionStore is source of truth for holdings (qty, entry price) — broker consulted only at startup for reconciliation
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
| Futu | Poll or callback | `BROKER=futu` + `futu-api` ([install guide](docs/futu-opend-install.md)) |
| IBKR | Callback | `BROKER=ibkr` + `ib_insync` |
| Alpaca | Poll | `BROKER=alpaca` + keys |

## Replay Mode

Same pipeline, historical data:

```bash
PYTHONPATH=. python3 -m src.live.replay --start 2025-01-01 --end 2025-06-01
```

## Testing

```bash
PYTHONPATH=. python -m pytest tests/ -q      # 263 tests
PYTHONPATH=. python -m pytest tests/ -q --cov=src   # with coverage
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
├── common/                    # Event bus, order_tracker, position_store, trading_logic, etc.
├── data/news/                 # NewsAPI, Finnhub, RSS, Reddit, Twitter
├── data/storage/              # ClickHouse
├── live/                      # Watcher, analyzer, trader, monitor, brokers, runners
└── strategies/                # Sentiment (keyword + LLM)
frontend/                      # React + Vite dashboard
scripts/                       # Data collection, startup, utils
tests/                         # 263 tests
```

## Data Stores

| Collection | Purpose | Writer | Reader(s) |
|---|---|---|---|
| `positions` | Current open positions (1 doc / symbol) with qty, entry price | OrderTracker (on fill) | SentimentTrader, PriceMonitor, Reconcile, API |
| `orders` | Full order lifecycle (pending → filled / failed / timeout) | TradeExecutor (submit), OrderTracker (update) | OrderTracker (poll) |
| `heartbeats` | Component health (updated every 30s) | All components | API |
| `logs` | Structured logs from all components (via MongoBatchHandler) | All components | Log Viewer tab |

**Design rule:** PositionStore is the canonical source for current holdings. Never infer positions from `orders` — always use `positions`.

## Deploy (VPS)

```bash
ssh user@your-vps
cd EonTrading
git pull
./scripts/start_distributed.sh restart    # stop all, start all with new code
./scripts/start_distributed.sh status     # verify all 7 components are running
```

Logs are in `logs/` — rotated automatically (10 MB each, 5 backups).

## Sentiment Analyzers

| Analyzer | When |
|----------|------|
| `KeywordSentimentAnalyzer` | Free, fast, no deps |
| `LLMSentimentAnalyzer` | More accurate, needs key |

Supports OpenAI, Azure OpenAI, and local Ollama.

## Roadmap

**Done:** Live pipeline (3 channels: [news], [sentiment], [trade]), 5 news sources, 4 brokers, single `orders` collection for order lifecycle, OrderTracker state machine (fill/fail/timeout), MongoDB persistence, dedup, 2 analyzers (keyword + LLM), SL/TP (trailing), backtesting (sentiment + price), React dashboard, single/distributed modes, Redis Streams, replay mode, price cache, transaction costs, Docker Compose deployment, heartbeats, graceful shutdown, 263 tests.

**To do:** Cross-source dedup, inverse ETF support, sector trading, real-news backtest, side-by-side comparison, live dashboard, Telegram alerts.
