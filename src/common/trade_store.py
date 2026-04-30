"""Shared trade document builder — single place to define the MongoDB trade schema."""


def trade_to_doc(symbol: str, action: str, price: float, shares: int,
                 reason: str, timestamp: str) -> dict:
    """Build a trade document for the trades/replay_trades collection."""
    return {
        "symbol": symbol,
        "action": action,
        "price": price,
        "shares": shares,
        "reason": reason,
        "timestamp": timestamp,
    }
