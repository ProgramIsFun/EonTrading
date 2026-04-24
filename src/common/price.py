"""Quick price lookup for live trading and replay mode."""
import yfinance as yf
from datetime import timedelta
from src.common.clock import clock


def get_price(symbol: str) -> float:
    """Get price for a symbol. Uses clock — live gets latest, replay gets historical."""
    try:
        if clock.is_replay:
            t = clock.now()
            start = (t - timedelta(days=5)).strftime("%Y-%m-%d")
            end = (t + timedelta(days=1)).strftime("%Y-%m-%d")
            data = yf.download(symbol, start=start, end=end, progress=False)
            if not data.empty:
                return float(data["Close"].iloc[-1].iloc[0]) if hasattr(data["Close"].iloc[-1], 'iloc') else float(data["Close"].iloc[-1])
        else:
            data = yf.download(symbol, period="1d", interval="1m", progress=False)
            if not data.empty:
                return float(data["Close"].iloc[-1].iloc[0]) if hasattr(data["Close"].iloc[-1], 'iloc') else float(data["Close"].iloc[-1])
    except Exception as e:
        print(f"  ⚠️ Price lookup failed for {symbol}: {e}")
    return 0.0
