"""WealthTracker: logs total portfolio wealth (cash + positions) every interval."""
import asyncio
import logging
from datetime import datetime

from src.common.clock import utcnow
from src.common.log_handler import ComponentFilter
from src.common.price import get_price

logger = logging.getLogger(__name__)
logger.addFilter(ComponentFilter("wealth"))


class WealthTracker:
    """Polls portfolio value at regular intervals, logs to file and MongoDB.

    wealth = cash + Σ(shares × current_price)

    Works with any broker — always calculates market value from prices
    rather than trusting broker-reported values.
    """

    def __init__(self, broker, position_store=None, interval_sec: int = 60):
        self.broker = broker
        self.position_store = position_store
        self.interval = interval_sec
        self._db = None
        self._history: list[dict] = []

    def _get_db(self):
        if self._db is None:
            from src.data.utils.db_helper import get_db
            self._db = get_db()
        return self._db

    async def snapshot(self) -> dict:
        """Take a single wealth snapshot. Returns {timestamp, cash, positions_value, wealth, positions}."""
        cash = await self.broker.get_cash()

        # Get positions from broker or position store
        if self.position_store:
            raw_positions = self.position_store.get_positions_with_prices()
            positions = {sym: info.get("qty", 0) for sym, info in raw_positions.items()}
        else:
            positions = await self.broker.get_positions()

        # Calculate market value of positions
        positions_value = 0.0
        position_details = {}
        for symbol, shares in positions.items():
            if shares <= 0:
                continue
            price = await asyncio.to_thread(get_price, symbol)
            if price > 0:
                value = shares * price
                positions_value += value
                position_details[symbol] = {"shares": shares, "price": price, "value": value}

        wealth = cash + positions_value
        ts = utcnow()

        return {
            "timestamp": ts.isoformat() + "Z",
            "cash": round(cash, 2),
            "positions_value": round(positions_value, 2),
            "wealth": round(wealth, 2),
            "positions": position_details,
        }

    def _save_to_mongodb(self, snapshot: dict):
        """Persist snapshot to MongoDB wealth_history collection."""
        try:
            db = self._get_db()
            db.wealth_history.insert_one({
                "timestamp": snapshot["timestamp"],
                "cash": snapshot["cash"],
                "positions_value": snapshot["positions_value"],
                "wealth": snapshot["wealth"],
                "positions": snapshot["positions"],
            })
        except Exception:
            logger.error("Failed to save wealth snapshot to MongoDB", exc_info=True)

    async def run(self):
        """Continuous monitoring loop."""
        logger.info("WealthTracker started, logging every %ds", self.interval)
        count = 0
        while True:
            try:
                snap = await self.snapshot()
                self._history.append(snap)
                self._save_to_mongodb(snap)

                count += 1
                pos_summary = ", ".join(
                    f"{sym}: {d['shares']}sh×${d['price']:.2f}=${d['value']:.0f}"
                    for sym, d in snap["positions"].items()
                ) or "none"
                logger.info(
                    "💰 Wealth #%d: $%.2f (cash: $%.2f + positions: $%.2f) | %s",
                    count, snap["wealth"], snap["cash"], snap["positions_value"], pos_summary,
                )
            except Exception as exc:
                logger.exception("WealthTracker.snapshot failed — %s", exc)
            await asyncio.sleep(self.interval)
