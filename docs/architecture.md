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
                   │  SentimentTrader │  threshold, min_confidence
                   │                  │  position sizing, cooldown
                   │  Decides:        │
                   │  BUY if sent > T │  (for each symbol in event)
                   │  SELL if sent <-T│
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
│  Features:                                 │
│  • Execute at next bar's open              │
│  • Slippage + commission (US_STOCKS)       │
│  • Stop-loss / Take-profit (intraday H/L)  │
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

## Event Bus

```
┌──────────┐    [news]     ┌──────────┐  [sentiment]  ┌──────────┐   [trade]   ┌──────────┐
│  News    ├──────────────►│Sentiment ├──────────────►│  Trader  ├────────────►│ Executor │
│  Watcher │               │ Analyzer │               │          │             │ (Broker) │
└──────────┘               └──────────┘               └──────────┘             └──────────┘

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

## Constraints

- **Cash only** — no margin, no leverage, no short selling, no borrowing
- Maximum loss is capped at initial capital
