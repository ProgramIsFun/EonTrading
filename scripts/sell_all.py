#!/usr/bin/env python3
"""Sell all open Futu positions (simulate or real).

Usage:
    PYTHONPATH=. python scripts/sell_all.py            # simulate (default)
    PYTHONPATH=. python scripts/sell_all.py --real     # real money
"""
import asyncio
import math
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("PYTHONPATH", os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()


async def main():
    from futu import TrdEnv, Market, SecurityType
    from src.common.factories import build_broker
    from src.settings import settings
    from src.live.brokers.broker import TradeEvent

    real = "--real" in sys.argv
    if real:
        settings.futu_real = True

    broker = build_broker()
    print(f"Broker: {broker.__class__.__name__} (simulate={broker.simulate})")

    ctx = await asyncio.to_thread(broker._get_ctx)
    trd_env = TrdEnv.SIMULATE if broker.simulate else TrdEnv.REAL

    def _query_positions():
        return ctx.position_list_query(trd_env=trd_env)

    ret, pos_data = await asyncio.to_thread(_query_positions)
    if ret != 0:
        print(f"Failed to query positions: {pos_data}")
        ctx.close()
        return

    sellable = []
    for _, row in pos_data.iterrows():
        code = row["code"]
        can_sell = int(row["can_sell_qty"])
        if can_sell > 0:
            sellable.append((code, can_sell))

    if not sellable:
        print("No sellable positions.")
        ctx.close()
        return

    print(f"\nFound {len(sellable)} sellable position(s):")
    for code, qty in sellable:
        print(f"  {code} × {qty}")

    from futu import OpenQuoteContext, Market, SecurityType
    quote_ctx = OpenQuoteContext(host=broker.host, port=broker.port)

    def _get_lot_sizes(codes):
        ret, info = quote_ctx.get_stock_basicinfo(Market.HK, SecurityType.STOCK, code_list=codes)
        if ret != 0:
            return {}
        return {row["code"]: row["lot_size"] for _, row in info.iterrows()}

    lot_sizes = await asyncio.to_thread(_get_lot_sizes, [c for c, _ in sellable])
    quote_ctx.close()

    print(f"\nSelling all positions...")
    for code, can_sell in sellable:
        lot_size = lot_sizes.get(code, 100)
        valid_qty = (can_sell // lot_size) * lot_size
        if valid_qty == 0:
            print(f"  ⚠️  {code} × {can_sell} — skipped (less than 1 lot of {lot_size})")
            continue

        trade = TradeEvent(
            symbol=broker._from_futu_code(code),
            action="sell",
            reason="sell_all script",
            timestamp="",
            size=float(valid_qty),
        )
        order_id = await broker.execute(trade)
        if order_id:
            print(f"  ✅ {code} × {valid_qty} → order {order_id}")
        else:
            print(f"  ❌ {code} × {valid_qty} → FAILED")

    print("\nDone.")
    ctx.close()


if __name__ == "__main__":
    asyncio.run(main())
