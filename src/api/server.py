"""REST API for EonTrading dashboard."""
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.common.clock import utcnow
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
_collector_stop = threading.Event()


def _run_collector():
    global _collector_running
    from src.common.news_poller import NewsPoller
    from src.data.news import RSSSource, RedditSource
    from datetime import datetime
    poller = NewsPoller(sources=[RSSSource(), RedditSource()])
    client = get_mongo_client()
    col = client["EonTradingDB"]["news"]
    col.create_index("url", unique=True, sparse=True)
    while _collector_running:
        for ev in poller.poll_once():
            if ev.url and col.find_one({"url": ev.url}):
                continue
            col.insert_one({
                "source": ev.source, "headline": ev.headline,
                "timestamp": ev.timestamp, "url": ev.url, "body": ev.body,
                "collected_at": utcnow().isoformat() + "Z",
            })
        if _collector_stop.wait(timeout=300):
            break


@app.get("/api/collector/status")
def collector_status():
    return {"running": _collector_running}


@app.post("/api/collector/start")
def collector_start():
    global _collector_task, _collector_running
    if _collector_running:
        return {"status": "already running"}
    _collector_running = True
    _collector_stop.clear()
    _collector_task = threading.Thread(target=_run_collector, daemon=True)
    _collector_task.start()
    return {"status": "started"}


@app.post("/api/collector/stop")
def collector_stop():
    global _collector_running
    _collector_running = False
    _collector_stop.set()
    return {"status": "stopped"}

from src.common.sample_news import SAMPLE_NEWS


@app.get("/api/health")
def health():
    try:
        client = get_mongo_client()
        db = client["EonTradingDB"]
        positions = list(db["positions"].find({}, {"_id": 0}))
        heartbeats = list(db["heartbeats"].find({}, {"_id": 0}))
        now = utcnow()
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
    except Exception as e:
        return {"status": "ok", "collector_running": _collector_running, "db_error": str(e)}


@app.get("/api/ping")
async def ping_components():
    """Real-time ping — asks all components to respond via event bus."""
    import os
    try:
        from src.common.event_bus import LocalEventBus, RedisStreamBus
        from src.common.ping import collect_pongs
        redis_host = os.getenv("REDIS_HOST")
        if redis_host:
            bus = RedisStreamBus(host=redis_host, group="api")
        else:
            bus = LocalEventBus()
        await bus.start()
        responses = await collect_pongs(bus, timeout=1.5)
        await bus.stop()
        return {"components": responses, "count": len(responses)}
    except Exception as e:
        return {"components": [], "count": 0, "error": str(e)}


@app.get("/api/reconcile")
async def reconcile_positions():
    """Compare system positions vs broker. Requires BROKER env var."""
    import os
    try:
        from src.common.reconcile import reconcile
        from src.live.brokers.broker import PaperBroker, FutuBroker, IBKRBroker, AlpacaBroker
        broker_name = os.getenv("BROKER", "log").lower()
        if broker_name == "futu":
            broker = FutuBroker(simulate=not os.getenv("FUTU_REAL"))
        elif broker_name == "ibkr":
            broker = IBKRBroker()
        elif broker_name == "alpaca":
            broker = AlpacaBroker()
        else:
            broker = PaperBroker()
        return await reconcile(broker)
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/docker/status")
def docker_status():
    """Get status of all Docker Compose services."""
    from src.common.docker_ctl import container_status
    return {"containers": container_status()}


@app.post("/api/docker/start/{name}")
def docker_start(name: str):
    """Start a component container. Use 'all' for full distributed pipeline."""
    from src.common.docker_ctl import start_component
    result = start_component(name)
    return {"component": name, **result}


@app.post("/api/docker/stop/{name}")
def docker_stop(name: str):
    """Stop a component container. Use 'all' to stop everything."""
    from src.common.docker_ctl import stop_component
    result = stop_component(name)
    return {"component": name, **result}


@app.post("/api/docker/restart/{name}")
def docker_restart(name: str):
    """Restart a component container."""
    from src.common.docker_ctl import restart_component
    result = restart_component(name)
    return {"component": name, **result}


@app.get("/api/docker/logs/{name}")
def docker_logs(name: str, lines: int = 50):
    """Get recent logs for a component."""
    from src.common.docker_ctl import view_logs
    result = view_logs(name, lines)
    return {"component": name, **result}


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


# --- Live pipeline backtest (background task) ---
_backtest_jobs: dict[str, dict] = {}


async def _run_live_backtest(job_id: str, params: dict):
    """Background task: runs the live pipeline backtest."""
    from src.common.event_bus import LocalEventBus
    from src.common.events import CHANNEL_NEWS, CHANNEL_FILL, NewsEvent
    from src.strategies.sentiment import KeywordSentimentAnalyzer, LLMSentimentAnalyzer
    from src.live.analyzer_service import AnalyzerService
    from src.live.sentiment_trader import SentimentTrader
    from src.live.brokers.broker import TradeExecutor, PaperBroker
    from src.common.trading_logic import TradingLogic
    from src.live.price_monitor import PriceMonitor
    from src.common.price import get_price
    from datetime import timedelta
    import os

    job = _backtest_jobs[job_id]
    try:
        capital = params["capital"]
        logic = TradingLogic(
            threshold=params["threshold"], min_confidence=0.15,
            max_allocation=params["max_allocation"],
            stop_loss_pct=params["stop_loss"], take_profit_pct=params["take_profit"],
        )

        bus = LocalEventBus()
        await bus.start()

        if params["analyzer"] == "llm" and os.getenv("OPENAI_API_KEY"):
            anlzr = LLMSentimentAnalyzer()
        else:
            anlzr = KeywordSentimentAnalyzer()

        broker = PaperBroker(initial_cash=capital, cost_model=US_STOCKS)
        monitor = PriceMonitor(bus, None, logic, interval_sec=0)
        trader = SentimentTrader(bus, logic=logic, broker=broker, price_monitor=monitor)
        analyzer_svc = AnalyzerService(bus, analyzer=anlzr, get_positions=lambda: trader.holdings)
        executor = TradeExecutor(bus, broker)

        fills = []
        await bus.subscribe(CHANNEL_FILL, lambda msg: fills.append(msg) or asyncio.sleep(0))

        async def on_fill(msg):
            fills.append(msg)

        await bus.subscribe(CHANNEL_FILL, on_fill)
        await analyzer_svc.start()
        await trader.start()
        await executor.start()

        equity = []
        prev_date = None
        sl_check_hours = params["sl_check_hours"]

        for i, doc in enumerate(SAMPLE_NEWS):
            curr = datetime.fromisoformat(doc["date"])

            if prev_date and monitor._states:
                check_time = prev_date + timedelta(hours=sl_check_hours)
                while check_time < curr:
                    await monitor.check_once(broker, as_of=check_time.isoformat())
                    await asyncio.sleep(0.05)
                    check_time += timedelta(hours=sl_check_hours)

            prev_date = curr
            await monitor.check_once(broker, as_of=doc["date"])
            await asyncio.sleep(0.05)

            event = NewsEvent(source="replay", headline=doc["headline"], timestamp=doc["date"], url="", body=doc["headline"])
            await bus.publish(CHANNEL_NEWS, event.to_dict())
            await asyncio.sleep(0.15)

            cash = await broker.get_cash()
            positions = await broker.get_positions()
            port_value = cash
            for sym, qty in positions.items():
                p = get_price(sym, as_of=doc["date"])
                if p > 0:
                    port_value += p * qty
            equity.append(round(port_value, 2))

            job["progress"] = round((i + 1) / len(SAMPLE_NEWS) * 100)

        await asyncio.sleep(0.3)
        await bus.stop()

        trades = []
        for f in fills:
            trades.append({
                "symbol": f.get("symbol", ""),
                "action": f.get("action", ""),
                "date": f.get("timestamp", ""),
                "price": 0, "shares": 0, "sentiment": 0, "pnl": 0,
                "headline": f.get("reason", ""),
            })

        final_cash = await broker.get_cash()
        final_positions = await broker.get_positions()
        final_value = final_cash
        last_date = SAMPLE_NEWS[-1]["date"]
        open_positions = []
        for sym, qty in final_positions.items():
            p = get_price(sym, as_of=last_date)
            val = p * qty
            final_value += val
            open_positions.append({"symbol": sym, "qty": qty, "price": round(p, 2), "value": round(val, 2)})

        total_return = (final_value - capital) / capital * 100
        peak = capital
        max_dd = 0
        for v in equity:
            if v > peak:
                peak = v
            dd = (peak - v) / peak * 100
            if dd > max_dd:
                max_dd = dd

        job["status"] = "done"
        job["result"] = {
            "mode": "live_pipeline",
            "analyzer": "llm" if isinstance(anlzr, LLMSentimentAnalyzer) else "keyword",
            "initial_capital": capital,
            "final_value": round(final_value, 2),
            "total_return_pct": round(total_return, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "total_trades": len(fills),
            "win_rate": 0,
            "equity_curve": equity,
            "trades": trades,
            "open_positions": open_positions,
            "cash": round(final_cash, 2),
        }
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)


@app.post("/api/live-backtest")
async def start_live_backtest(
    capital: float = 70000,
    threshold: float = 0.4,
    max_allocation: float = 0.2,
    stop_loss: float = 0.05,
    take_profit: float = 0.10,
    max_hold_days: int = 30,
    sl_check_hours: int = 24,
    analyzer: str = "keyword",
):
    """Start a live pipeline backtest as a background task."""
    import uuid
    job_id = str(uuid.uuid4())[:8]
    _backtest_jobs[job_id] = {"status": "running", "progress": 0}
    params = dict(capital=capital, threshold=threshold, max_allocation=max_allocation,
                  stop_loss=stop_loss, take_profit=take_profit, max_hold_days=max_hold_days,
                  sl_check_hours=sl_check_hours, analyzer=analyzer)
    asyncio.create_task(_run_live_backtest(job_id, params))
    return {"job_id": job_id, "status": "running"}


@app.get("/api/live-backtest/{job_id}")
def get_live_backtest(job_id: str):
    """Poll backtest status/result."""
    job = _backtest_jobs.get(job_id)
    if not job:
        return {"status": "not_found"}
    if job["status"] == "done":
        result = job["result"]
        del _backtest_jobs[job_id]  # cleanup
        return {"status": "done", **result}
    return {"status": job["status"], "progress": job.get("progress", 0)}


@app.get("/api/news")
def news(limit: int = 100):
    try:
        client = get_mongo_client()
        col = client["EonTradingDB"]["news"]
        docs = list(col.find({}, {"_id": 0}).sort("collected_at", -1).limit(limit))
        return docs
    except Exception as e:
        return {"error": f"MongoDB unavailable: {e}", "fallback": True, "articles": SAMPLE_NEWS}


@app.get("/api/news/count")
def news_count():
    try:
        client = get_mongo_client()
        col = client["EonTradingDB"]["news"]
        return {"count": col.count_documents({})}
    except Exception:
        return {"count": 0}
