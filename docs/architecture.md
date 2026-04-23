# System Architecture

## Live Trading Pipeline

```
┌─────────────────────────────────────────────────────────────────────┐
│                         NEWS SOURCES                                │
│                                                                     │
│   NewsAPI        Finnhub         RSS Feeds        Reddit            │
│   (API key)      (API key)       (free)           (free)            │
└──────┬──────────────┬──────────────┬──────────────────┬─────────────┘
       │              │              │                  │
       └──────────────┴──────┬───────┴──────────────────┘
                             │
                             ▼
                   ┌──────────────────┐
                   │   NewsWatcher    │  Polls every 120s
                   │   (dedup + batch)│  Publishes to [news] channel
                   └────────┬─────────┘
                            │
                            ▼ EventBus [news]
                            │
                   ┌────────┴─────────┐
                   │    Sentiment     │  Keyword or LLM
                   │    Analyzer      │  Extracts: symbols, sentiment,
                   │                  │  confidence, urgency
                   └────────┬─────────┘
                            │
                            ▼ EventBus [sentiment]
                            │
                   ┌────────┴─────────┐
                   │  SentimentTrader │  ┌──────────────┐
                   │                  │◄─┤ TradingLogic │ (shared)
                   │  Decides:        │  └──────────────┘
                   │  BUY if sent > T │  threshold, SL/TP, trailing,
                   │  SELL if sent <-T│  position sizing, cooldown
                   └────────┬─────────┘
                            │
                            ▼ EventBus [trade]
                            │
                   ┌────────┴─────────┐
                   │  TradeExecutor   │
                   │                  │
                   │  ┌─────────────┐ │
                   │  │  LogBroker  │ │  Dry run (default)
                   │  │  FutuBroker │ │  HK market via OpenD
                   │  └─────────────┘ │
                   └──────────────────┘
```

## Backtest Pipeline

```
┌──────────────────┐     ┌──────────────────┐
│  Synthetic or    │     │    yfinance       │
│  Historical News │     │  (hourly/daily)   │
│  (with dates)    │     │                   │
└────────┬─────────┘     └────────┬──────────┘
         │                        │
         ▼                        ▼
┌────────────────────────────────────────────┐
│           Backtest Engine                  │
│                                            │
│  News → Analyzer → Signals → Execution     │
│                                            │
│  ┌──────────────┐                          │
│  │ TradingLogic │ (same as live trader)    │
│  └──────────────┘                          │
│  • Execute at next bar's open              │
│  • Slippage + commission (US_STOCKS)       │
│  • Stop-loss / Take-profit (intraday H/L)  │
│  • Trailing stop-loss                      │
│  • Max hold period                         │
│  • Cooldown between trades                 │
│  • Position sizing:                        │
│    - Sentiment-scaled                      │
│    - Max allocation cap                    │
│    - Risk-per-trade                        │
│                                            │
│  Modes:                                    │
│  • Single symbol  (sentiment_backtest.py)  │
│  • Multi-symbol portfolio (portfolio_backtest.py) │
└────────────────────────────────────────────┘
```

## Dashboard

```
┌──────────────────────────────────────────────┐
│  React + TypeScript + Vite (frontend/)       │
│                                              │
│  ┌────────────┐ ┌──────────┐ ┌───────────┐  │
│  │ ParamsPanel│ │StatsCard │ │EquityChart│  │
│  │ (sliders)  │ │(return,  │ │(recharts) │  │
│  │            │ │ DD, win%)│ │           │  │
│  └────────────┘ └──────────┘ └───────────┘  │
│  ┌──────────────────────────────────────┐    │
│  │ TradeTable (log with P&L)           │    │
│  └──────────────────────────────────────┘    │
└──────────────────┬───────────────────────────┘
                   │ HTTP
                   ▼
┌──────────────────────────────────────────────┐
│  FastAPI (src/api/server.py)                 │
│                                              │
│  GET /api/backtest?capital=...&threshold=...  │
│  GET /api/news                               │
│  GET /api/health                             │
└──────────────────┬───────────────────────────┘
                   │
                   ▼
          Backtest Engine (above)
```

## Event Bus

```
Backends:
  • LocalEventBus  — in-process, zero latency
  • RedisEventBus  — cross-process, ~1-5ms (Redis on Windows PC)
```

## Sentiment Analyzers

```
┌─────────────────────────────────┐
│  BaseSentimentAnalyzer          │  Interface
│  analyze(NewsEvent) → Sentiment │
├─────────────────────────────────┤
│                                 │
│  KeywordSentimentAnalyzer       │  Fast, free, no deps
│  • TICKER_MAP: company → symbol │  • "apple" → AAPL
│  • BULLISH/BEARISH word lists   │  • "surge" → +1, "crash" → -1
│  • Confidence = keyword density │
│                                 │
│  LLMSentimentAnalyzer           │  Accurate, needs API key
│  • OpenAI-compatible API        │  • Understands context
│  • Works with Ollama/local LLMs │  • Returns structured JSON
│                                 │
└─────────────────────────────────┘
```

## Shared Components

```
TradingLogic (src/common/trading_logic.py)
├── should_buy()          — threshold + confidence + position sizing
├── should_sell_on_sentiment() — bearish threshold check
├── check_stop_loss()     — fixed or trailing SL
├── check_take_profit()   — fixed TP
└── update_peak()         — trailing SL peak tracking

Used by:
  • Backtest engine (portfolio_backtest.py)
  • Live trader (news_trader.py → SentimentTrader)
```

## Constraints

- **Cash only** — no margin, no leverage, no short selling, no borrowing
- Maximum loss is capped at initial capital
