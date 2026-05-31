"""Reconciliation: compare system positions vs broker positions.

Run daily or on startup to catch discrepancies.
"""
import logging

from src.common.clock import utcnow
from src.common.position_store import PositionStore

logger = logging.getLogger(__name__)


async def reconcile(broker, store: PositionStore = None) -> dict:
    """Compare MongoDB positions vs broker account. Returns discrepancies."""
    store = store or PositionStore()
    our_positions = store.get_positions_with_prices()  # {symbol: {entryTime, entryPrice, qty}}
    broker_positions = await broker.get_positions()  # {symbol: qty}
    broker_cash = await broker.get_cash()

    our_symbols = set(our_positions.keys())
    broker_symbols = set(broker_positions.keys())

    missing_in_broker = our_symbols - broker_symbols  # we think we own, broker says no
    missing_in_system = broker_symbols - our_symbols  # broker has, we don't know about
    matched = our_symbols & broker_symbols

    issues = []
    for sym in missing_in_broker:
        issues.append({"symbol": sym, "issue": "in system but not in broker", "severity": "high",
                        "system_qty": our_positions[sym].get("qty", 0)})
    for sym in missing_in_system:
        issues.append({"symbol": sym, "issue": "in broker but not in system", "severity": "high",
                        "broker_qty": broker_positions[sym]})
    for sym in matched:
        our_qty = our_positions[sym].get("qty", 0)
        broker_qty = broker_positions[sym]
        if our_qty != broker_qty:
            issues.append({"symbol": sym, "issue": "qty mismatch", "severity": "medium",
                            "system_qty": our_qty, "broker_qty": broker_qty})

    result = {
        "timestamp": utcnow().isoformat() + "Z",
        "our_positions": {s: our_positions[s] for s in our_symbols},
        "broker_positions": {s: q for s, q in broker_positions.items()},
        "broker_cash": broker_cash,
        "matched": list(matched),
        "issues": issues,
        "ok": len(issues) == 0,
    }

    status = "✅" if result["ok"] else "⚠️"
    logger.info("%s Reconciliation @ %s", status, result["timestamp"])
    logger.info("System positions: %s", list(our_symbols) or "none")
    logger.info("Broker positions: %s", dict(broker_positions) or "none")
    logger.info("Broker cash: $%s", f"{broker_cash:,.2f}")
    if issues:
        for i in issues:
            logger.warning("🚨 %s: %s", i["symbol"], i["issue"])
    else:
        logger.info("All %d position(s) match.", len(matched))

    return result
