"""Reconciliation: compare system positions vs broker positions.

Run daily or on startup to catch discrepancies.
"""
from datetime import datetime
from src.common.position_store import PositionStore


async def reconcile(broker, store: PositionStore = None) -> dict:
    """Compare MongoDB positions vs broker account. Returns discrepancies."""
    store = store or PositionStore()
    our_positions = store.get_positions()  # {symbol: entry_time}
    broker_positions = await broker.get_positions()  # {symbol: qty}
    broker_cash = await broker.get_cash()

    our_symbols = set(our_positions.keys())
    broker_symbols = set(broker_positions.keys())

    missing_in_broker = our_symbols - broker_symbols  # we think we own, broker says no
    missing_in_system = broker_symbols - our_symbols  # broker has, we don't know about
    matched = our_symbols & broker_symbols

    issues = []
    for sym in missing_in_broker:
        issues.append({"symbol": sym, "issue": "in system but not in broker", "severity": "high"})
    for sym in missing_in_system:
        issues.append({"symbol": sym, "issue": "in broker but not in system", "severity": "high",
                        "broker_qty": broker_positions[sym]})

    result = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "our_positions": list(our_symbols),
        "broker_positions": {s: q for s, q in broker_positions.items()},
        "broker_cash": broker_cash,
        "matched": list(matched),
        "issues": issues,
        "ok": len(issues) == 0,
    }

    # Print summary
    status = "✅" if result["ok"] else "⚠️"
    print(f"\n  {status} Reconciliation @ {result['timestamp']}")
    print(f"  System positions: {list(our_symbols) or 'none'}")
    print(f"  Broker positions: {dict(broker_positions) or 'none'}")
    print(f"  Broker cash: ${broker_cash:,.2f}")
    if issues:
        for i in issues:
            print(f"  🚨 {i['symbol']}: {i['issue']}")
    else:
        print(f"  All {len(matched)} position(s) match.")

    return result
