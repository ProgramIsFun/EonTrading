"""REST API for EonTrading dashboard."""
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.backtest.portfolio_backtest import run_portfolio_backtest
from src.common.costs import US_STOCKS
from src.data.utils.db_helper import get_mongo_client
import asyncio
import threading
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="EonTrading API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- News collector state ---
_collector_task = None
_collector_running = False


def _run_collector():
    global _collector_running
    from src.common.news_poller import NewsPoller
    from src.data.news import RSSSource, RedditSource
    from datetime import datetime
    poller = NewsPoller(sources=[RSSSource(), RedditSource()])
    client = get_mongo_client()
    col = client["EonTradingDB"]["news"]
    col.create_index("url", unique=True, sparse=True)
    import time
    while _collector_running:
        for ev in poller.poll_once():
            if ev.url and col.find_one({"url": ev.url}):
                continue
            col.insert_one({
                "source": ev.source, "headline": ev.headline,
                "timestamp": ev.timestamp, "url": ev.url, "body": ev.body,
                "collected_at": datetime.utcnow().isoformat() + "Z",
            })
        time.sleep(300)


@app.get("/api/collector/status")
def collector_status():
    return {"running": _collector_running}


@app.post("/api/collector/start")
def collector_start():
    global _collector_task, _collector_running
    if _collector_running:
        return {"status": "already running"}
    _collector_running = True
    _collector_task = threading.Thread(target=_run_collector, daemon=True)
    _collector_task.start()
    return {"status": "started"}


@app.post("/api/collector/stop")
def collector_stop():
    global _collector_running
    _collector_running = False
    return {"status": "stopped"}

# Sample news for demo — replace with DB later
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


@app.get("/api/health")
def health():
    try:
        client = get_mongo_client()
        db = client["EonTradingDB"]
        positions = list(db["positions"].find({}, {"_id": 0}))
        heartbeats = list(db["heartbeats"].find({}, {"_id": 0}))
        now = datetime.utcnow()
        components = []
        for hb in heartbeats:
            last = hb.get("lastBeat")
            age = (now - last).total_seconds() if last else 999
            components.append({
                "component": hb.get("component"),
                "status": "🟢 running" if age < 60 else "🔴 stale" if age < 300 else "⚫ dead",
                "lastBeat": last.isoformat() + "Z" if last else None,
                "ageSec": round(age),
                "host": hb.get("host"),
                "pid": hb.get("pid"),
                **{k: v for k, v in hb.items() if k not in ("component", "lastBeat", "host", "pid")},
            })
        return {
            "status": "ok",
            "collector_running": _collector_running,
            "open_positions": len(positions),
            "positions": [{"symbol": p.get("symbol"), "entryTime": p.get("entryTime")} for p in positions],
            "components": components,
        }
    except Exception:
        return {"status": "ok", "collector_running": _collector_running}


@app.get("/api/ping")
async def ping_components():
    """Real-time ping — asks all components to respond via event bus."""
    import os
    try:
        from src.common.event_bus import LocalEventBus, RedisEventBus
        from src.common.ping import collect_pongs
        redis_host = os.getenv("REDIS_HOST")
        if redis_host:
            bus = RedisEventBus(host=redis_host)
        else:
            bus = LocalEventBus()
        await bus.start()
        responses = await collect_pongs(bus, timeout=1.5)
        await bus.stop()
        return {"components": responses, "count": len(responses)}
    except Exception as e:
        return {"components": [], "count": 0, "error": str(e)}


@app.get("/api/trades")
def trades(limit: int = 100):
    """Return recent confirmed trades from the trades collection."""
    try:
        client = get_mongo_client()
        col = client["EonTradingDB"]["trades"]
        docs = list(col.find({}, {"_id": 0}).sort("timestamp", -1).limit(limit))
        return docs
    except Exception:
        return []


@app.get("/api/price-backtest")
def price_backtest(
    symbol: str = "AAPL",
    strategy: str = "sma",
    start: str = "2025-01-01",
    end: str = "2025-12-31",
    capital: float = 10000,
    # SMA params
    fast: int = 20,
    slow: int = 50,
    # RSI params
    period: int = 14,
    oversold: float = 30,
    overbought: float = 70,
):
    import yfinance as yf
    from src.backtest import run_backtest
    from src.strategies import SMACrossover, RSIMeanReversion

    df = yf.download(symbol, start=start, end=end, auto_adjust=True, progress=False)
    if df.empty:
        return {"error": f"No data for {symbol}"}
    df = df.reset_index()
    df.columns = [c.lower() if isinstance(c, str) else c[0].lower() for c in df.columns]
    if "date" in df.columns:
        df = df.rename(columns={"date": "timestamp"})

    if strategy == "rsi":
        strat = RSIMeanReversion(period=period, oversold=oversold, overbought=overbought)
    else:
        strat = SMACrossover(fast=fast, slow=slow)

    result = run_backtest(df, strat, symbol=symbol, initial_capital=capital, cost_model=US_STOCKS)
    return {
        "strategy": result.strategy,
        "symbol": result.symbol,
        "initial_capital": result.initial_capital,
        "final_value": round(result.final_value, 2),
        "total_return_pct": round(result.total_return_pct, 2),
        "annual_return_pct": round(result.annual_return_pct, 2),
        "max_drawdown_pct": round(result.max_drawdown_pct, 2),
        "total_trades": result.total_trades,
        "win_rate": round(result.win_rate, 1),
        "sharpe_ratio": round(result.sharpe_ratio, 2),
        "equity_curve": [round(v, 2) for v in result.equity_curve.tolist()],
        "trades": [
            {"symbol": t.symbol, "side": t.side, "entry_price": round(t.entry_price, 2),
             "exit_price": round(t.exit_price, 2), "shares": t.shares, "pnl": round(t.pnl, 2),
             "entry_date": str(t.entry_date)[:10], "exit_date": str(t.exit_date)[:10]}
            for t in result.trades
        ],
    }


@app.get("/api/backtest")
def backtest(
    capital: float = 70000,
    threshold: float = 0.4,
    max_allocation: float = 0.2,
    stop_loss: float = 0.05,
    take_profit: float = 0.10,
    max_hold_days: int = 30,
    trailing_sl: bool = False,
):
    result = run_portfolio_backtest(
        news_events=SAMPLE_NEWS,
        start="2025-01-01", end="2025-12-31",
        initial_capital=capital,
        threshold=threshold, min_confidence=0.15,
        cost_model=US_STOCKS,
        max_allocation=max_allocation,
        stop_loss_pct=stop_loss, take_profit_pct=take_profit,
        max_hold_days=max_hold_days,
        trailing_sl=trailing_sl,
    )
    return {
        "initial_capital": result.initial_capital,
        "final_value": round(result.final_value, 2),
        "total_return_pct": round(result.total_return_pct, 2),
        "max_drawdown_pct": round(result.max_drawdown_pct, 2),
        "total_trades": result.total_trades,
        "win_rate": round(result.win_rate, 1),
        "equity_curve": [round(v, 2) for v in result.equity_curve.tolist()],
        "trades": [
            {
                "symbol": t.symbol, "action": t.action, "date": t.date,
                "price": round(t.price, 2), "shares": t.shares,
                "sentiment": round(t.sentiment, 2), "pnl": round(t.pnl, 2),
                "headline": t.headline,
            }
            for t in result.trades
        ],
    }


@app.get("/api/news")
def news(limit: int = 100):
    try:
        client = get_mongo_client()
        col = client["EonTradingDB"]["news"]
        docs = list(col.find({}, {"_id": 0}).sort("collected_at", -1).limit(limit))
        return docs
    except Exception:
        return SAMPLE_NEWS


@app.get("/api/news/count")
def news_count():
    try:
        client = get_mongo_client()
        col = client["EonTradingDB"]["news"]
        return {"count": col.count_documents({})}
    except Exception:
        return {"count": 0}
