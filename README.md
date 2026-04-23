# EonTrading

Trading system: data collection, backtesting, and live execution.

**Scope:** This project trades with cash only — no margin, no leverage, no short selling, no borrowing from brokers. This ensures maximum loss is capped at the initial capital. Borrowed positions (margin/shorts) carry the risk of losing more than you put in.

## Architecture

```
Mac (dev machine)  ──────>  Windows PC (192.168.0.38)
  - Code & scripts            - ClickHouse (Docker, port 8123/9000)
  - Strategy dev               - AiRelay (port 3200, key: see .env)
  - Backtesting                - Data storage (~134 MB for S&P 500 daily)
```

**Data flow:** yfinance → Python ingestion → ClickHouse (on Windows)

**Databases:**
- **ClickHouse** (`eontrading` db) — all OHLCV price data (time series)
- **MongoDB** (`EonTradingDB`) — symbols list, configs, metadata

## Project Structure

```
src/
├── data/
│   ├── providers/              # Data source adapters
│   │   ├── base_provider.py        # Abstract MarketDataProvider interface
│   │   └── yfinance_provider.py    # YFinance implementation (HK + US stocks)
│   ├── storage/                # Database backends
│   │   ├── base_storage.py         # Abstract StorageBackend interface
│   │   └── clickhouse_storage.py   # ClickHouse implementation
│   ├── ingest/                 # Data ingestion pipelines
│   │   └── yfinance_ingest.py      # Batch ingest from yfinance → ClickHouse
│   ├── news/                   # News data sources
│   │   └── newsapi_source.py       # NewsAPI.org integration
│   └── utils/
│       └── db_helper.py            # MongoDB connection helper
├── strategies/                 # Strategy definitions
│   ├── base_strategy.py            # Strategy + Signal interfaces
│   ├── sma_crossover.py            # SMA crossover (price-based)
│   ├── rsi_mean_reversion.py       # RSI mean reversion (price-based)
│   └── sentiment.py                # Sentiment analyzers (keyword + LLM)
├── backtest/                   # Backtesting engine
│   └── engine.py                   # Backtest runner with costs, SL/TP, shorting
├── live/                       # Live trading
│   ├── brokers/
│   │   └── futu_broker.py          # Futu OpenD integration (HK market)
│   └── news_trader.py              # News sentiment live trader
└── common/                     # Shared infrastructure
    ├── costs.py                    # Transaction cost models (US, HK, crypto)
    ├── events.py                   # Event schemas (NewsEvent, SentimentEvent, TradeEvent)
    └── event_bus.py                # Pub/sub (LocalEventBus, RedisEventBus)
scripts/                        # Runnable scripts
config/                         # Symbol lists, env configs
docs/                           # Reference material
```

## Roadmap

### Done
- [x] Live pipeline: news → sentiment → trade → broker (event bus)
- [x] 4 news sources: NewsAPI, Finnhub, RSS, Reddit
- [x] 2 sentiment analyzers: keyword, LLM
- [x] Sentiment backtest with hourly data and realistic execution
- [x] Risk management: SL/TP, trailing SL, hold limits, cooldown
- [x] Position sizing: sentiment-scaled, max allocation, risk-per-trade
- [x] Multi-symbol portfolio backtest with shared capital
- [x] Shared TradingLogic between backtest and live trader
- [x] Dashboard: React + Vite + FastAPI (equity chart, trade log, param controls)
- [x] Real news backtest: 7 stocks with actual 2025 events
- [x] P&L by symbol bar chart
- [x] News feed tab with collector start/stop from dashboard
- [x] News notification badge (polls every 30s)
- [x] News collector: RSS + Reddit → MongoDB (EonTradingDB.news)
- [x] News backfill script: Finnhub + NewsAPI → MongoDB
- [x] Architecture diagram in dashboard (About tab) with file paths
- [x] Max hold days in live trader (off by default)
- [x] Shared NewsPoller across NewsWatcher, collector, and API
- [x] Split components into separate files (news_watcher, sentiment_trader, broker)
- [x] Distributed mode: separate process runners via RedisEventBus
- [x] Single process fallback via LocalEventBus
- [x] TwitterSource interface (official API + alternative placeholder)
- [x] Price-based backtest tab (SMA crossover, RSI mean reversion)
- [x] 43 tests passing

### To Do — Strategy
- [ ] LLM analyzer — keyword misses context ("growth slows" = bearish)
- [ ] Sector-based trading — "tariffs on China" should trigger tech stocks
- [ ] Backtest with collected real news from MongoDB
- [ ] Urgency-based position sizing

### To Do — Dashboard
- [ ] Compare runs side by side
- [ ] Live mode: real-time positions and trade history

### To Do — Engine
- [ ] Persist positions/trades to MongoDB (survive restarts)
- [ ] Multi-timeframe: daily sentiment + hourly execution

### To Do — Infra
- [ ] Deploy API to Windows PC alongside ClickHouse
- [ ] Telegram/webhook alerts before executing trades
- [ ] Set up Ollama on Windows PC for free local LLM
- [ ] Try `twscrape` library for TwitterSource implementation

## Setup

### Prerequisites
- Python 3.11+
- ClickHouse running on Windows PC (Docker)
- MongoDB Atlas (for symbols/metadata)

### Install dependencies
```bash
pip install -e .                    # core deps
pip install -e ".[backtest]"        # + backtesting
pip install -e ".[futu]"            # + Futu broker
pip install -e ".[dev]"             # + jupyter/notebooks
```

### macOS SSL fix (if needed)
```bash
# Add to ~/.zshrc
export SSL_CERT_FILE=$(python3 -c "import certifi; print(certifi.where())")
```

## ClickHouse

### Start (on Windows PC)
```bash
docker run -d --name clickhouse \
  -p 8123:8123 -p 9000:9000 \
  -v clickhouse-data:/var/lib/clickhouse \
  -e CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT=1 \
  -e CLICKHOUSE_PASSWORD= \
  clickhouse/clickhouse-server
```

### Schema
Database: `eontrading`, Table: `ohlcv`

| Column    | Type                | Notes |
|-----------|---------------------|-------|
| symbol    | String              | e.g. AAPL, 0700.HK |
| exchange  | String              | US, HK, CRYPTO |
| interval  | Enum8               | 1s, 1m, 5m, 15m, 1h, 1d, 1w |
| timestamp | DateTime64(3, UTC)  | millisecond precision |
| open      | Float64             | |
| high      | Float64             | |
| low       | Float64             | |
| close     | Float64             | |
| volume    | Float64             | |

Engine: `ReplacingMergeTree()`, ordered by `(symbol, interval, timestamp)`, partitioned by `toYear(timestamp)`. Duplicate rows (same symbol+interval+timestamp) are automatically deduplicated.

### Connect from Python
```python
from src.data.storage import ClickHouseStorage
storage = ClickHouseStorage(host="192.168.0.38")
df = storage.query_ohlcv("AAPL", "1d", start, end)
```

## Data

### Current data
- **S&P 500 daily** — 503 symbols, 4.3M+ rows, 1962–2026 (134 MB compressed)

### Backfill
```bash
PYTHONPATH=. python scripts/backfill_sp500.py
```

### Data sources
| Source | Markets | Granularity | Limits |
|--------|---------|-------------|--------|
| yfinance | US, HK, global | 1d: 20+ years, 1m: last 30 days | Free, rate limited |
| Futu OpenD | HK, US | Real-time tick | Free with account |
| Binance | Crypto | Real-time tick | Free |

## Strategies

### Price-based (for backtesting)
Strategies output signals (`1`=buy, `-1`=sell, `0`=hold) or rich `Signal` objects with per-trade size/SL/TP.

| Strategy | File | Description |
|----------|------|-------------|
| SMA Crossover | `sma_crossover.py` | Buy when fast MA crosses above slow MA |
| RSI Mean Reversion | `rsi_mean_reversion.py` | Buy oversold, sell overbought |

### Sentiment-based (for live trading)
Pluggable sentiment analyzers score news headlines and drive trading decisions.

| Analyzer | When to use |
|----------|-------------|
| `KeywordSentimentAnalyzer` | Free, fast, no deps. Good enough for testing. |
| `LLMSentimentAnalyzer` | More accurate. Works with OpenAI, Ollama, or any OpenAI-compatible API. |

```python
# Keyword (default)
analyzer = KeywordSentimentAnalyzer()

# OpenAI
analyzer = LLMSentimentAnalyzer()  # uses OPENAI_API_KEY env var

# Local Ollama
analyzer = LLMSentimentAnalyzer(base_url="http://localhost:11434/v1", model="llama3", api_key="ollama")
```

### Backtest engine features
| Feature | Flag | Default |
|---------|------|---------|
| Next-bar open execution | `exec_next_open` | on |
| Short selling | `allow_short` | off |
| Stop-loss | `stop_loss_pct` | off |
| Take-profit | `take_profit_pct` | off |
| Position sizing | `position_size` | 100% |
| Transaction costs | `cost_model` | ZERO |

## Live Trading

### News sentiment trader
Polls news sources, scores sentiment, trades automatically.

```bash
# Keyword analyzer (free)
NEWSAPI_KEY=your_key PYTHONPATH=. python -m src.live.news_trader

# LLM analyzer (more accurate)
NEWSAPI_KEY=your_key OPENAI_API_KEY=your_key PYTHONPATH=. python -m src.live.news_trader
```

Architecture: `NewsAPI → NewsWatcher → SentimentAnalyzer → EventBus → SentimentTrader`

See [Event System docs](docs/event-system.md) for details on pub/sub, message schemas, and backends.

## Brokers
| Broker | Markets | Status |
|--------|---------|--------|
| Futu | HK, US stocks | Basic integration (src/live/brokers/futu_broker.py) |
| Webull | US stocks | Planned |
| Binance | Crypto | Planned |

## Docs
- [Event System](docs/event-system.md) — pub/sub architecture, message schemas, EventBus backends
- [General Trading Info](docs/general-info.md) — options, warrants, terminology

## Testing

### Unit tests (no external deps, runs anywhere)
```bash
PYTHONPATH=. python -m pytest tests/ -v
```
- `tests/test_costs.py` — cost model math
- `tests/test_strategies.py` — signal generation logic
- `tests/test_backtest.py` — engine: PnL, drawdown, Sharpe, stop-loss, shorting

All use synthetic in-memory data. No ClickHouse or network needed.

### Integration scripts (need ClickHouse on Windows PC)
```bash
PYTHONPATH=. python scripts/test_ingest.py      # ingest 3 symbols → query back
PYTHONPATH=. python scripts/test_backtest.py     # fetch AAPL from ClickHouse → backtest
PYTHONPATH=. python scripts/backfill_sp500.py    # bulk load S&P 500 history
```

## Related repos (archived)
- [EonTrading-DataGrabber](https://github.com/ProgramIsFun/EonTrading-DataGrabber) — absorbed into src/data/
- [EonTrading-Futu](https://github.com/ProgramIsFun/EonTrading-Futu) — absorbed into src/live/brokers/
- [EonTrading-Core](https://github.com/ProgramIsFun/EonTrading-Core) — broker research/examples (reference)
- [EonTrading-Webull](https://github.com/ProgramIsFun/EonTrading-Webull) — notebooks (reference)
