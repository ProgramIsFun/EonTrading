"""Replay the SAMPLE_NEWS through the live pipeline — same settings as the backtest API.

Usage: PYTHONPATH=. python scripts/backtest/replay_live_backtest.py
"""
import asyncio
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv()

from src.common.sample_news import SAMPLE_NEWS


async def main():
    from src.common.event_bus import LocalEventBus
    from src.common.events import CHANNEL_NEWS, NewsEvent
    from src.strategies.sentiment import KeywordSentimentAnalyzer
    from src.live.analyzer_service import AnalyzerService
    from src.live.sentiment_trader import SentimentTrader
    from src.live.brokers.broker import TradeExecutor, PaperBroker
    from src.common.trading_logic import TradingLogic
    from src.common.costs import US_STOCKS

    # Same settings as the backtest API
    logic = TradingLogic(
        threshold=0.4,
        min_confidence=0.15,
        max_allocation=0.2,
        stop_loss_pct=0.05,
        take_profit_pct=0.10,
    )

    bus = LocalEventBus()
    await bus.start()

    from src.live.price_monitor import PriceMonitor
    from src.common.position_store import PositionStore

    analyzer = KeywordSentimentAnalyzer()
    broker = PaperBroker(initial_cash=70000, cost_model=US_STOCKS)
    store = PositionStore(collection="replay_positions")

    # Clean slate — clear positions from previous runs
    store.set_positions({})

    monitor = PriceMonitor(bus, store, logic, interval_sec=0)

    trader = SentimentTrader(bus, logic=logic, broker=broker, price_monitor=monitor, position_store=store)
    analyzer_svc = AnalyzerService(bus, analyzer=analyzer, get_positions=lambda: trader.holdings)
    executor = TradeExecutor(bus, broker)

    await analyzer_svc.start()
    await trader.start()
    await executor.start()

    print(f"\n{'═' * 60}")
    print(f"  Replay Backtest via Live Pipeline")
    print(f"  Capital: $70,000 | Threshold: 0.4 | Max alloc: 20%")
    print(f"  SL: 5% | TP: 10%")
    print(f"  Analyzer: Keyword | Broker: PaperBroker (dry run)")
    print(f"  News events: {len(SAMPLE_NEWS)}")
    print(f"{'═' * 60}\n")

    # SL/TP check interval between news events (hours)
    # 1 = hourly (matches original backtest, slow), 24 = daily (faster)
    SL_CHECK_INTERVAL = int(os.getenv("SL_CHECK_HOURS", "24"))

    prev_date = None
    for doc in SAMPLE_NEWS:
        curr = datetime.fromisoformat(doc["date"])

        # Simulate periodic SL/TP checks between news events
        if prev_date and monitor._states:
            check_time = prev_date + timedelta(hours=SL_CHECK_INTERVAL)
            while check_time < curr:
                sold = await monitor.check_once(broker, as_of=check_time.isoformat())
                if sold:
                    print(f"    ⏰ SL/TP check @ {check_time.strftime('%Y-%m-%d %H:%M')}")
                    await asyncio.sleep(0.3)
                check_time += timedelta(hours=SL_CHECK_INTERVAL)

        prev_date = curr

        # Check SL/TP at this timestamp before processing news
        sold = await monitor.check_once(broker, as_of=doc["date"])
        if sold:
            await asyncio.sleep(0.3)

        print(f"\n  📅 {doc['date']} — {doc['headline'][:70]}")

        event = NewsEvent(
            source="replay",
            headline=doc["headline"],
            timestamp=doc["date"],
            url="",
            body=doc["headline"],
        )
        await bus.publish(CHANNEL_NEWS, event.to_dict())
        await asyncio.sleep(0.2)  # let pipeline process

    await asyncio.sleep(0.5)

    # Summary
    cash = await broker.get_cash()
    positions = await broker.get_positions()

    # Price open positions at end of replay period
    from src.common.price import get_price
    last_date = SAMPLE_NEWS[-1]["date"]
    portfolio_value = cash
    print(f"\n{'═' * 60}")
    print(f"  Replay Complete")
    print(f"{'─' * 60}")
    print(f"  {'Symbol':<8s} {'Qty':>5s} {'Avg Cost':>10s} {'Current':>10s} {'Value':>12s} {'P&L':>10s}")
    print(f"  {'─'*8} {'─'*5} {'─'*10} {'─'*10} {'─'*12} {'─'*10}")
    for symbol, qty in positions.items():
        current_price = get_price(symbol, as_of=last_date)
        value = current_price * qty
        # cost basis from broker's tracked cash changes
        portfolio_value += value
        print(f"  {symbol:<8s} {qty:>5d} {'':>10s} ${current_price:>9.2f} ${value:>11,.2f}")

    pnl = portfolio_value - 70000
    pnl_pct = (pnl / 70000) * 100
    print(f"  {'─'*8} {'─'*5} {'─'*10} {'─'*10} {'─'*12} {'─'*10}")
    print(f"  Cash remaining:    ${cash:,.2f}")
    print(f"  Positions value:   ${portfolio_value - cash:,.2f}")
    print(f"  Total value:       ${portfolio_value:,.2f}")
    print(f"  P&L:               ${pnl:+,.2f} ({pnl_pct:+.1f}%)")
    print(f"  Initial capital:   $70,000.00")
    print(f"{'═' * 60}\n")


if __name__ == "__main__":
    asyncio.run(main())
