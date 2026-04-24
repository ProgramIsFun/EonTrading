"""Replay with pre-scored LLM sentiment — skips analyzer, feeds directly to trader.

The sentiment scores below simulate what an LLM would output for each headline.
The rest of the pipeline (trader, executor, monitor) runs identically to live mode.

Usage:
  REDIS_HOST=localhost PRICE_SOURCE=clickhouse PYTHONPATH=. python3 scripts/backtest/live_pipeline_llm_backtest.py
"""
import asyncio
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv()

# Pre-scored sentiment — simulates LLM analyzer output
SCORED_NEWS = [
    {"date": "2025-01-06T10:00:00", "headline": "Nvidia unveils new Blackwell GPU chips at CES, stock rallies",
     "symbols": ["NVDA"], "sentiment": 0.7, "confidence": 0.85, "urgency": "normal"},
    {"date": "2025-01-27T09:30:00", "headline": "DeepSeek AI model shocks market, Nvidia stock crashes on cheaper AI fears",
     "symbols": ["NVDA"], "sentiment": -0.9, "confidence": 0.95, "urgency": "high"},
    {"date": "2025-01-29T16:30:00", "headline": "Meta Q4 earnings beat estimates, ad revenue growth accelerates",
     "symbols": ["META"], "sentiment": 0.8, "confidence": 0.90, "urgency": "normal"},
    {"date": "2025-01-30T16:30:00", "headline": "Apple reports record Q1 revenue of $124B, beating estimates",
     "symbols": ["AAPL"], "sentiment": 0.8, "confidence": 0.90, "urgency": "normal"},
    {"date": "2025-02-06T16:30:00", "headline": "Amazon Q4 earnings beat estimates, AWS revenue growth accelerates",
     "symbols": ["AMZN"], "sentiment": 0.7, "confidence": 0.85, "urgency": "normal"},
    {"date": "2025-02-14T10:00:00", "headline": "Meta announces massive AI spending increase to $65B, stock drops on cost fears",
     "symbols": ["META"], "sentiment": -0.8, "confidence": 0.90, "urgency": "high"},
    {"date": "2025-02-26T16:30:00", "headline": "Nvidia Q4 earnings smash records, data center revenue surges 93%",
     "symbols": ["NVDA"], "sentiment": 0.9, "confidence": 0.95, "urgency": "high"},
    {"date": "2025-03-12T10:00:00", "headline": "Google acquires cloud security firm Wiz for $32B, biggest deal ever",
     "symbols": ["GOOGL"], "sentiment": 0.6, "confidence": 0.80, "urgency": "normal"},
    {"date": "2025-04-03T14:00:00", "headline": "Trump announces sweeping tariffs on China, Apple supply chain at risk",
     "symbols": ["AAPL"], "sentiment": -0.9, "confidence": 0.95, "urgency": "high"},
    {"date": "2025-04-09T15:00:00", "headline": "Trump pauses tariffs for 90 days, Apple stock surges on relief rally",
     "symbols": ["AAPL"], "sentiment": 0.5, "confidence": 0.70, "urgency": "normal"},
    {"date": "2025-04-23T10:00:00", "headline": "Elon Musk says he will reduce DOGE role to focus on Tesla, stock surges",
     "symbols": ["TSLA"], "sentiment": 0.7, "confidence": 0.80, "urgency": "normal"},
    {"date": "2025-04-24T16:30:00", "headline": "Alphabet Q1 earnings beat estimates, cloud revenue surges, stock rallies",
     "symbols": ["GOOGL"], "sentiment": 0.8, "confidence": 0.90, "urgency": "normal"},
    {"date": "2025-04-30T16:30:00", "headline": "Meta Q1 earnings crush expectations, revenue up 16% on strong ad demand",
     "symbols": ["META"], "sentiment": 0.8, "confidence": 0.90, "urgency": "normal"},
    {"date": "2025-04-30T16:30:00", "headline": "Microsoft Q3 earnings crush estimates, Azure growth reaccelerates to 35%",
     "symbols": ["MSFT"], "sentiment": 0.8, "confidence": 0.90, "urgency": "normal"},
    {"date": "2025-05-01T16:30:00", "headline": "Apple Q2 earnings beat expectations, services revenue hits record",
     "symbols": ["AAPL"], "sentiment": 0.7, "confidence": 0.85, "urgency": "normal"},
]


async def main():
    import time
    t0 = time.time()
    def elapsed():
        return f"[{time.time()-t0:.1f}s]"

    from src.common.event_bus import LocalEventBus
    from src.common.events import CHANNEL_SENTIMENT, SentimentEvent
    from src.live.sentiment_trader import SentimentTrader
    from src.live.brokers.broker import TradeExecutor, PaperBroker
    from src.common.costs import US_STOCKS
    from src.common.trading_logic import TradingLogic
    from src.live.price_monitor import PriceMonitor
    from src.common.position_store import PositionStore

    print(f"  {elapsed()} imports done")

    logic = TradingLogic(
        threshold=0.4, min_confidence=0.15,
        max_allocation=0.2, stop_loss_pct=0.05, take_profit_pct=0.10,
    )

    bus = LocalEventBus()
    await bus.start()
    print(f"  {elapsed()} bus started")

    broker = PaperBroker(initial_cash=70000, cost_model=US_STOCKS)
    store = PositionStore(collection="replay_positions")
    store.set_positions({})
    print(f"  {elapsed()} store cleared")

    monitor = PriceMonitor(bus, store, logic, interval_sec=0)
    trader = SentimentTrader(bus, logic=logic, broker=broker, price_monitor=monitor, position_store=store)
    executor = TradeExecutor(bus, broker)

    await trader.start()
    await executor.start()

    SL_CHECK_INTERVAL = int(os.getenv("SL_CHECK_HOURS", "24"))

    import os as _os
    VERBOSE = _os.getenv("VERBOSE", "")

    # Pre-load all prices into memory for fast SL/TP checks
    if os.getenv("PRICE_SOURCE", "").lower() == "clickhouse":
        from src.common.price import _price_cache
        from src.data.storage.clickhouse_storage import ClickHouseStorage
        storage = ClickHouseStorage()
        symbols = list({s for doc in SCORED_NEWS for s in doc["symbols"]})
        start_date = SCORED_NEWS[0]["date"][:10]
        end_date = SCORED_NEWS[-1]["date"][:10]
        print(f"  {elapsed()} Pre-loading prices for {symbols} ({start_date} → {end_date})...")
        for sym in symbols:
            for interval in ["1h", "1d"]:
                df = storage.query_ohlcv(sym, interval, start_date, end_date)
                if df.empty:
                    continue
                for _, row in df.iterrows():
                    ts = row["timestamp"]
                    if hasattr(ts, "tz_convert") and ts.tzinfo:
                        ts = ts.tz_convert(None)
                    key = f"{sym}:{ts.strftime('%Y-%m-%d-%H')}"
                    _price_cache[key] = float(row["close"])
                print(f"    {sym} ({interval}): {len(df)} candles")
        print(f"  {elapsed()} Cache: {len(_price_cache)} entries in memory\n")

    print(f"\n{'═' * 60}")
    print(f"  Replay Backtest — Pre-scored LLM Sentiment")
    print(f"  Capital: $70,000 | Threshold: 0.4 | Max alloc: 20%")
    print(f"  SL: 5% | TP: 10% | SL check: every {SL_CHECK_INTERVAL}h")
    print(f"  Analyzer: Pre-scored (LLM simulation)")
    print(f"  News events: {len(SCORED_NEWS)}")
    print(f"{'═' * 60}\n")

    # Suppress price logs unless VERBOSE=1
    if not VERBOSE:
        import src.common.price as _price_mod
        _orig_yf = _price_mod._from_yfinance
        _orig_ch = _price_mod._from_clickhouse
        def _quiet_yf(symbol, as_of=None):
            import io, sys
            old = sys.stdout; sys.stdout = io.StringIO()
            r = _orig_yf(symbol, as_of); sys.stdout = old; return r
        def _quiet_ch(symbol, as_of=None):
            import io, sys
            old = sys.stdout; sys.stdout = io.StringIO()
            r = _orig_ch(symbol, as_of); sys.stdout = old; return r
        _price_mod._from_yfinance = _quiet_yf
        _price_mod._from_clickhouse = _quiet_ch

    prev_date = None
    checks_done = 0
    for doc in SCORED_NEWS:
        curr = datetime.fromisoformat(doc["date"])

        # SL/TP checks between events
        if prev_date and monitor._states:
            check_time = prev_date + timedelta(hours=SL_CHECK_INTERVAL)
            while check_time < curr:
                if not monitor._states:
                    break
                sold = monitor.check_once_sync(as_of=check_time.isoformat())
                checks_done += 1
                if sold:
                    for sym, price, qty in sold:
                        from src.common.events import TradeEvent, CHANNEL_TRADE
                        trade = TradeEvent(symbol=sym, action="sell",
                                           reason=f"SL/TP @ ${price:.2f}",
                                           timestamp=check_time.isoformat(), price=price, size=float(qty))
                        await bus.publish(CHANNEL_TRADE, trade.to_dict())
                    print(f"    ⏰ SL/TP @ {check_time.strftime('%Y-%m-%d %H:%M')} — sold {', '.join(s[0] for s in sold)}")
                    await asyncio.sleep(0.05)
                elif checks_done % 500 == 0:
                    print(f"    {elapsed()} ... {checks_done} SL/TP checks (@ {check_time.strftime('%Y-%m-%d %H:%M')})")
                check_time += timedelta(hours=SL_CHECK_INTERVAL)

        prev_date = curr

        # Check SL/TP at event time
        sold = await monitor.check_once(broker, as_of=doc["date"])
        if sold:
            await asyncio.sleep(0.05)

        print(f"\n  {elapsed()} 📅 {doc['date']} — {doc['headline'][:65]}")
        print(f"     sentiment: {doc['sentiment']:+.1f}  confidence: {doc['confidence']}  symbols: {doc['symbols']}")

        # Publish pre-scored sentiment directly — skip analyzer
        sentiment = SentimentEvent(
            source="llm-prescored",
            headline=doc["headline"],
            timestamp=doc["date"],
            analyzed_at=doc["date"],
            symbols=doc["symbols"],
            sentiment=doc["sentiment"],
            confidence=doc["confidence"],
            urgency=doc["urgency"],
        )
        await bus.publish(CHANNEL_SENTIMENT, sentiment.to_dict())
        await asyncio.sleep(0.2)

    await asyncio.sleep(0.5)

    # Summary
    cash = await broker.get_cash()
    positions = await broker.get_positions()
    from src.common.price import get_price
    last_date = SCORED_NEWS[-1]["date"]
    portfolio_value = cash
    print(f"\n{'═' * 60}")
    print(f"  Replay Complete (LLM pre-scored)")
    print(f"{'─' * 60}")
    print(f"  {'Symbol':<8s} {'Qty':>5s} {'Current':>10s} {'Value':>12s}")
    print(f"  {'─'*8} {'─'*5} {'─'*10} {'─'*12}")
    for symbol, qty in positions.items():
        current_price = get_price(symbol, as_of=last_date)
        value = current_price * qty
        portfolio_value += value
        print(f"  {symbol:<8s} {qty:>5d} ${current_price:>9.2f} ${value:>11,.2f}")

    pnl = portfolio_value - 70000
    pnl_pct = (pnl / 70000) * 100
    print(f"  {'─'*8} {'─'*5} {'─'*10} {'─'*12}")
    print(f"  Cash remaining:    ${cash:,.2f}")
    print(f"  Positions value:   ${portfolio_value - cash:,.2f}")
    print(f"  Total value:       ${portfolio_value:,.2f}")
    print(f"  P&L:               ${pnl:+,.2f} ({pnl_pct:+.1f}%)")
    print(f"  Initial capital:   $70,000.00")
    print(f"{'═' * 60}\n")


if __name__ == "__main__":
    asyncio.run(main())
