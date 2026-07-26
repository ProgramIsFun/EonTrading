"""WebullBroker — Webull Markets via OpenAPI SDK."""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from src.common.events import TradeEvent
from src.common.log_handler import ComponentFilter
from src.settings import settings

from .broker import AccountInfo, Broker, FillStatus

logger = logging.getLogger(__name__)
logger.addFilter(ComponentFilter("executor"))


class WebullBroker(Broker):
    """pip install webull-openapi-python-sdk

    Uses Webull OpenAPI for US stock trading.
    """

    def __init__(self, app_key: str = "", app_secret: str = "", region: str = "us",
                 account_id: str = ""):
        self.app_key = app_key or settings.webull_app_key
        self.app_secret = app_secret or settings.webull_app_secret
        self.region = region
        self.account_id = account_id or settings.webull_account_id
        self._client: Any = None

    def _connect(self):
        if self._client is not None:
            return
        try:
            from webull.core.client import ApiClient
            from webull.trade.trade_client import TradeClient
            api_client = ApiClient(self.app_key, self.app_secret, self.region)
            api_client.add_endpoint(self.region, f"openapi.webull.com")
            self._client = TradeClient(api_client)
        except Exception as e:
            raise ConnectionError(f"Webull connect failed: {e}") from e

    async def execute(self, trade: TradeEvent) -> str | None:
        try:
            async with self._safe(f"execute({trade.symbol})"):
                assert self._client is not None
                client_order_id = uuid.uuid4().hex
                new_orders = [{
                    "combo_type": "NORMAL",
                    "client_order_id": client_order_id,
                    "symbol": trade.symbol,
                    "instrument_type": "EQUITY",
                    "market": "US",
                    "order_type": "MARKET",
                    "quantity": str(int(trade.size)),
                    "side": "BUY" if trade.action == "buy" else "SELL",
                    "time_in_force": "DAY",
                    "entrust_type": "QTY",
                }]

                def _place():
                    return self._client.order_v3.place_order(self.account_id, new_orders)
                res = await asyncio.to_thread(_place)
                if res.status_code == 200:
                    data = res.json()
                    order_id = data.get("orderId") or data.get("order_id") or client_order_id
                    logger.info("📤 Webull order placed: %s %s (id=%s)", trade.action.upper(), trade.symbol, order_id)
                    return str(order_id)
                logger.error("Webull order rejected: %s %s — %s", trade.action.upper(), trade.symbol, res.text)
                return None
        except Exception:
            return None

    async def check_order(self, order_id: str) -> FillStatus:
        try:
            async with self._safe(f"check_order({order_id})"):
                assert self._client is not None

                def _query():
                    return self._client.order_v3.get_order_detail(self.account_id, order_id)
                res = await asyncio.to_thread(_query)
                if res.status_code != 200:
                    return FillStatus(status="pending")
                data = res.json()
                order_status = data.get("orderStatus", data.get("order_status", ""))
                filled_qty = int(float(data.get("filledQty", data.get("filled_qty", 0))))
                filled_price = float(data.get("filledPrice", data.get("filled_price", 0.0)))
                if order_status in ("FILLED", "FINAL_FILLED"):
                    return FillStatus(status="filled", filled_qty=filled_qty, filled_price=filled_price)
                if order_status in ("CANCELED", "FAILED", "REJECTED"):
                    return FillStatus(status="cancelled", reason=order_status)
                return FillStatus(status="pending")
        except Exception:
            return FillStatus(status="pending")

    async def cancel_order(self, order_id: str) -> bool:
        try:
            async with self._safe(f"cancel_order({order_id})"):
                assert self._client is not None

                def _cancel():
                    return self._client.order_v3.cancel_order(self.account_id, order_id)
                res = await asyncio.to_thread(_cancel)
                if res.status_code != 200:
                    logger.warning("Webull cancel_order failed: %s", res.text)
                return bool(res.status_code == 200)
        except Exception:
            return False

    async def get_positions(self) -> dict[str, int]:
        try:
            async with self._safe("get_positions"):
                assert self._client is not None

                def _query():
                    return self._client.account_v2.get_account_positions(self.account_id)
                res = await asyncio.to_thread(_query)
                if res.status_code != 200:
                    logger.warning("Webull get_positions failed: %s", res.text)
                    return {}
                data = res.json()
                positions = {}
                for pos in data.get("positions", []):
                    symbol = pos.get("symbol", "")
                    qty = int(float(pos.get("quantity", 0)))
                    if qty > 0:
                        positions[symbol] = qty
                return positions
        except Exception:
            return {}

    async def get_account_info(self) -> AccountInfo:
        try:
            async with self._safe("get_account_info"):
                assert self._client is not None

                def _query():
                    return self._client.account_v2.get_account_balance(self.account_id)
                res = await asyncio.to_thread(_query)
                if res.status_code == 200:
                    data = res.json()
                    return AccountInfo(
                        cash=float(data.get("availableCash", data.get("available_cash", 0.0))),
                        buying_power=float(data.get("buyingPower", data.get("buying_power", 0.0))),
                        market_value=float(data.get("portfolioValue", data.get("portfolio_value", 0.0))),
                        total_assets=float(data.get("totalAssets", data.get("total_assets", 0.0))),
                    )
                logger.warning("Webull get_account_info failed: %s", res.text)
        except Exception:
            pass
        return AccountInfo()
