# Event System

Real-time communication between components using publish/subscribe.

## Architecture

```
News Watcher ──> [news] ──> Sentiment Analyzer ──> [sentiment] ──> Trader ──> [trade] ──> Executor
```

Each arrow is an EventBus channel. Components are decoupled — they only know about the message format, not each other.

## Channels & Events

| Channel | Event Type | Publisher | Consumer |
|---------|-----------|-----------|----------|
| `news` | `NewsEvent` | News watchers | Sentiment analyzer |
| `sentiment` | `SentimentEvent` | Sentiment analyzer | Traders/strategies |
| `trade` | `TradeEvent` | Traders | Execution engine, logger |

## Event Schemas

### NewsEvent (raw news)
```python
{
    "source": "newsapi",                    # newsapi, truthsocial, reddit, finnhub
    "headline": "Trump announces tariffs",
    "timestamp": "2026-04-22T10:05:00Z",
    "url": "https://...",
    "body": "Full article text..."          # optional
}
```

### SentimentEvent (analyzed)
```python
{
    "source": "newsapi",
    "headline": "Trump announces tariffs",
    "timestamp": "2026-04-22T10:05:00Z",   # when news happened
    "analyzed_at": "2026-04-22T10:05:02Z",  # when we scored it
    "symbols": ["AAPL", "NVDA"],            # affected tickers
    "sector": "technology",
    "sentiment": -0.7,                      # -1.0 (bearish) to +1.0 (bullish)
    "confidence": 0.85,                     # 0.0 to 1.0
    "urgency": "high"                       # low, normal, high
}
```

### TradeEvent (action)
```python
{
    "symbol": "AAPL",
    "action": "sell",
    "reason": "sentiment:-0.7 on tariff news",
    "timestamp": "2026-04-22T10:05:03Z",
    "price": 0.0,                           # 0 = market order
    "size": 1.0                             # fraction of capital
}
```

## EventBus Backends

### LocalEventBus (default)
- In-process, zero latency
- Multiple subscribers supported
- No extra infrastructure
- All components must run in the same Python process

```python
from src.common.event_bus import LocalEventBus

bus = LocalEventBus()
```

### RedisEventBus
- Cross-process, cross-machine (~1-5ms latency)
- Message persistence with Redis Streams (future)
- Requires Redis running (Docker)

```python
from src.common.event_bus import RedisEventBus

bus = RedisEventBus(host="192.168.0.38", port=6379)
```

Start Redis on Windows:
```bash
docker run -d --name redis -p 6379:6379 redis
```

## Usage

```python
import asyncio
from src.common.event_bus import LocalEventBus
from src.common.events import NewsEvent, SentimentEvent, CHANNEL_NEWS, CHANNEL_SENTIMENT

bus = LocalEventBus()

# Subscribe
async def on_news(msg):
    event = NewsEvent.from_dict(msg)
    print(f"Got news: {event.headline}")

await bus.subscribe(CHANNEL_NEWS, on_news)
await bus.start()

# Publish
event = NewsEvent(source="newsapi", headline="...", timestamp="...")
await bus.publish(CHANNEL_NEWS, event.to_dict())
```

## Switching Backends

Change one line — no other code changes needed:

```python
# Development (same process)
bus = LocalEventBus()

# Production (distributed)
bus = RedisEventBus(host="192.168.0.38")
```
