"""Quick price lookup for live trading."""
import yfinance as yf


def get_price(symbol: str) -> float:
    """Get latest price for a symbol. Returns 0.0 on failure."""
    try:
        data = yf.download(symbol, period="1d", interval="1m", progress=False)
        if not data.empty:
            return float(data["Close"].iloc[-1])
    except Exception as e:
        print(f"  ⚠️ Price lookup failed for {symbol}: {e}")
    return 0.0
