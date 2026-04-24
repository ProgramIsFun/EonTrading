# Event System

Real-time communication between components using publish/subscribe.

## Architecture

```
News Watcher → [news] → Analyzer → [sentiment] → Trader → [trade] → Executor → Broker
                                                     ↑                              ↓
                                                     └──────── [fill] ──────────────┘
```

Each arrow is an EventBus channel. Components are decoupled — they only know about the message format, not each other.

## Channels & Events

| Channel | Event Type | Publisher | Consumer |
|---------|-----------|-----------|----------|
| `news` | `NewsEvent` | NewsWatcher | AnalyzerService |
| `sentiment` | `SentimentEvent` | AnalyzerService | SentimentTrader |
| `trade` | `TradeEvent` | SentimentTrader | TradeExecutor |
| `fill` | `FillEvent` | Broker (via Executor) | SentimentTrader |

## Event Schemas

### NewsEvent (raw news)
```python
{
    "source": "newsapi",
    "headline": "Trump announces tariffs",
    "timestamp": "2026-04-22T10:05:00Z",
    "url": "https://...",
    "body": "Full article text..."
}
```

### SentimentEvent (analyzed)
```python
{
    "source": "newsapi",
    "headline": "Trump announces tariffs",
    "timestamp": "2026-04-22T10:05:00Z",
    "analyzed_at": "2026-04-22T10:05:02Z",
    "symbols": ["AAPL", "NVDA"],
    "sector": "technology",
    "sentiment": -0.7,       # -1.0 (bearish) to +1.0 (bullish)
    "confidence": 0.85,      # 0.0 to 1.0
    "urgency": "high"        # low, normal, high
}
```

### TradeEvent (order request)
```python
{
    "symbol": "AAPL",
    "action": "sell",
    "reason": "sentiment:-0.7 on tariff news",
    "timestamp": "2026-04-22T10:05:03Z",
    "price": 0.0,            # 0 = market order
    "size": 1.0              # fraction of capital
}
```

### FillEvent (broker confirmation)
```python
{
    "symbol": "AAPL",
    "action": "sell",
    "success": true,          # did the broker fill the order?
    "reason": "filled",       # or error message
    "timestamp": "2026-04-22T10:05:05Z"
}
```

## Trade Lifecycle

1. Trader decides to buy/sell → updates in-memory, marks symbol as **pending**
2. Publishes `TradeEvent` to `[trade]`
3. Executor forwards to Broker
4. Broker confirms/rejects (each broker does this differently):
   - `LogBroker`: instant
   - `FutuBroker`: polls order status
   - `IBKRBroker`: callback via ib_insync
   - `AlpacaBroker`: polls REST API
5. Broker publishes `FillEvent` to `[fill]`
6. Trader receives fill:
   - **Success** → persist to MongoDB, log trade
   - **Failure** → rollback in-memory state

Pending symbols block duplicate orders until the fill arrives.

## EventBus Backends

### LocalEventBus (default)
- In-process, zero latency
- All components in one Python process

```python
bus = LocalEventBus()
```

### RedisEventBus
- Cross-process, cross-machine
- Requires Redis running

```python
bus = RedisEventBus(host="192.168.0.38")
```

Same component code, both modes. Components don't know which bus they're on.
