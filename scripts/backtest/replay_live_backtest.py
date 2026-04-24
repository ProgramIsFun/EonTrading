"""Replay the SAMPLE_NEWS through the live pipeline — same settings as the backtest API.

Usage: PYTHONPATH=. python scripts/backtest/replay_live_backtest.py
"""
import asyncio
import os
from dotenv import load_dotenv
load_dotenv()

SAMPLE_NEWS = [
    {"date": "2025-01-06T10:00:00", "headline": "Nvidia unveils new Blackwell GPU chips at CES, stock rallies"},
    {"date": "2025-01-27T09:30:00", "headline": "DeepSeek AI model shocks market, Nvidia stock crashes on cheaper AI fears"},
    {"date": "2025-01-29T16:30:00", "headline": "Meta Q4 earnings beat estimates, ad revenue growth accelerates"},
    {"date": "2025-01-30T16:30:00", "headline": "Apple reports record Q1 revenue of $124B, beating estimates"},
    {"date": "2025-02-06T16:30:00", "headline": "Amazon Q4 earnings beat estimates, AWS revenue growth accelerates"},
    {"date": "2025-02-14T10:00:00", "headline": "Meta announces massive AI spending increase to $65B, stock drops on cost fears"},
    {"date": "2025-02-26T16:30:00", "headline": "Nvidia Q4 earnings smash records, data center revenue surges 93%"},
    {"date": "2025-03-12T10:00:00", "headline": "Google acquires cloud security firm Wiz for $32B, biggest deal ever"},
    {"date": "2025-04-03T14:00:00", "headline": "Trump announces sweeping tariffs on China, Apple supply chain at risk"},
    {"date": "2025-04-09T15:00:00", "headline": "Trump pauses tariffs for 90 days, Apple stock surges on relief rally"},
    {"date": "2025-04-23T10:00:00", "headline": "Elon Musk says he will reduce DOGE role to focus on Tesla, stock surges"},
    {"date": "2025-04-24T16:30:00", "headline": "Alphabet Q1 earnings beat estimates, cloud revenue surges, stock rallies"},
    {"date": "2025-04-30T16:30:00", "headline": "Meta Q1 earnings crush expectations, revenue up 16% on strong ad demand"},
    {"date": "2025-04-30T16:30:00", "headline": "Microsoft Q3 earnings crush estimates, Azure growth reaccelerates to 35%"},
    {"date": "2025-05-01T16:30:00", "headline": "Apple Q2 earnings beat expectations, services revenue hits record"},
]


async def main():
    from src.common.clock import clock
    from src.common.event_bus import LocalEventBus
    from src.common.events import CHANNEL_NEWS, NewsEvent
    from src.strategies.sentiment import KeywordSentimentAnalyzer
    from src.live.analyzer_service import AnalyzerService
    from src.live.sentiment_trader import SentimentTrader
    from src.live.brokers.broker import TradeExecutor, LogBroker
    from src.common.trading_logic import TradingLogic

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
    broker = LogBroker(initial_cash=70000)
    store = PositionStore()
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
    print(f"  Analyzer: Keyword | Broker: LogBroker (dry run)")
    print(f"  News events: {len(SAMPLE_NEWS)}")
    print(f"{'═' * 60}\n")

    for doc in SAMPLE_NEWS:
        clock.set_time(doc["date"])

        # Check SL/TP at this timestamp before processing news
        await monitor.check_once(broker)
        await asyncio.sleep(0.1)

        print(f"\n  📅 {clock.now().strftime('%Y-%m-%d %H:%M')} — {doc['headline'][:70]}")

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
    clock.reset()

    # Summary
    cash = await broker.get_cash()
    positions = await broker.get_positions()

    # Price open positions at end of replay period
    from src.common.price import get_price
    clock.set_time(SAMPLE_NEWS[-1]["date"])  # price at last news date
    portfolio_value = cash
    print(f"\n{'═' * 60}")
    print(f"  Replay Complete")
    print(f"{'─' * 60}")
    print(f"  {'Symbol':<8s} {'Qty':>5s} {'Avg Cost':>10s} {'Current':>10s} {'Value':>12s} {'P&L':>10s}")
    print(f"  {'─'*8} {'─'*5} {'─'*10} {'─'*10} {'─'*12} {'─'*10}")
    for symbol, qty in positions.items():
        current_price = get_price(symbol)
        value = current_price * qty
        # cost basis from broker's tracked cash changes
        portfolio_value += value
        print(f"  {symbol:<8s} {qty:>5d} {'':>10s} ${current_price:>9.2f} ${value:>11,.2f}")

    clock.reset()

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
