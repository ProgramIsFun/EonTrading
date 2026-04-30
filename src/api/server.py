"""REST API for EonTrading dashboard."""
import logging
import os
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from src.common.clock import utcnow
from src.backtest.portfolio_backtest import run_portfolio_backtest
from src.common.costs import US_STOCKS
from src.data.utils.db_helper import get_mongo_client
import asyncio
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

app = FastAPI(title="EonTrading API")

_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:8000").split(",")
app.add_middleware(CORSMiddleware, allow_origins=_cors_origins, allow_methods=["*"], allow_headers=["*"])

# --- API key auth (optional — set API_KEY env var to enable) ---
_api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)
_API_KEY = os.getenv("API_KEY")


async def _check_api_key(key: str = Depends(_api_key_header)):
    if _API_KEY and key != _API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


# --- Docker component allowlist ---
_ALLOWED_DOCKER_NAMES = {"watcher", "analyzer", "trader", "executor", "redis", "all"}


def _validate_docker_name(name: str) -> str:
    if name not in _ALLOWED_DOCKER_NAMES:
        raise HTTPException(status_code=400, detail=f"Unknown component: {name}")
    return name

from src.common.sample_news import SAMPLE_NEWS


@app.get("/api/health")
def health():
    try:
        client = get_mongo_client()
        db = client["EonTradingDB"]
        positions = list(db["positions"].find({}, {"_id": 0}))
        return {
            "status": "ok",
            "open_positions": len(positions),
            "positions": [{"symbol": p.get("symbol"), "entryTime": p.get("entryTime")} for p in positions],
        }
    except Exception as e:
        logger.warning("Health check DB error: %s", e)
        return {"status": "ok", "db_error": str(e)}


@app.get("/api/queues")
def queue_status():
    """Show message counts in all Redis Streams."""
    try:
        import redis
        r = redis.Redis(host=os.getenv("REDIS_HOST", "localhost"), port=6379, decode_responses=True)
        r.ping()
        streams = ["news", "sentiment", "trade", "fill"]
        result = {}
        for name in streams:
            key = f"stream:{name}"
            try:
                result[name] = r.xlen(key)
            except Exception:
                result[name] = 0
        return {"queues": result}
    except Exception as e:
        logger.warning("Queue status error: %s", e)
        return {"queues": {}, "error": str(e)}


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
        logger.warning("Ping error: %s", e)
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
        logger.error("Reconcile error: %s", e)
        return {"ok": False, "error": str(e)}


@app.get("/api/docker/status")
def docker_status():
    """Get status of all Docker Compose services."""
    from src.common.docker_ctl import container_status, container_env
    containers = container_status()
    # Attach watcher options from running container
    for c in containers:
        if c["name"] == "watcher" and c["state"] == "running":
            env = container_env("watcher")
            c["options"] = {
                "persist_news": env.get("PERSIST_NEWS") == "1",
                "publish_pipeline": env.get("PUBLISH_PIPELINE") == "1",
            }
    return {"containers": containers}


@app.post("/api/docker/start/{name}", dependencies=[Depends(_check_api_key)])
def docker_start(name: str, persist_news: bool = False, publish_pipeline: bool = True):
    """Start a component container. Use 'all' for full distributed pipeline."""
    _validate_docker_name(name)
    from src.common.docker_ctl import start_component
    env = {}
    if name == "watcher":
        env["PERSIST_NEWS"] = "1" if persist_news else "0"
        env["PUBLISH_PIPELINE"] = "1" if publish_pipeline else "0"
    result = start_component(name, env=env if env else None)
    return {"component": name, **result}


@app.post("/api/docker/stop/{name}", dependencies=[Depends(_check_api_key)])
def docker_stop(name: str):
    """Stop a component container. Use 'all' to stop everything."""
    _validate_docker_name(name)
    from src.common.docker_ctl import stop_component
    result = stop_component(name)
    return {"component": name, **result}


@app.post("/api/docker/restart/{name}", dependencies=[Depends(_check_api_key)])
def docker_restart(name: str):
    """Restart a component container."""
    _validate_docker_name(name)
    from src.common.docker_ctl import restart_component
    result = restart_component(name)
    return {"component": name, **result}


@app.get("/api/docker/logs/{name}")
def docker_logs(name: str, lines: int = Query(default=50, ge=1, le=1000)):
    """Get recent logs for a component."""
    _validate_docker_name(name)
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
        logger.warning("Failed to fetch trades from MongoDB", exc_info=True)
        return []


@app.get("/api/price-backtest")
def price_backtest(
    symbol: str = "AAPL",
    strategy: str = "sma",
    start: str = "2025-01-01",
    end: str = "2025-12-31",
    capital: float = Query(default=10000, ge=100, le=100_000_000),
    # SMA params
    fast: int = Query(default=20, ge=2, le=500),
    slow: int = Query(default=50, ge=2, le=500),
    # RSI params
    period: int = Query(default=14, ge=2, le=200),
    oversold: float = Query(default=30, ge=0, le=100),
    overbought: float = Query(default=70, ge=0, le=100),
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
    capital: float = Query(default=70000, ge=100, le=100_000_000),
    threshold: float = Query(default=0.4, ge=0, le=1),
    max_allocation: float = Query(default=0.2, ge=0.01, le=1),
    stop_loss: float = Query(default=0.05, ge=0.001, le=0.5),
    take_profit: float = Query(default=0.10, ge=0.001, le=5.0),
    max_hold_days: int = Query(default=30, ge=1, le=365),
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
_JOB_TTL_SEC = 600  # auto-cleanup jobs older than 10 minutes


def _cleanup_stale_jobs():
    """Remove backtest jobs that have been sitting around too long (prevents memory leak)."""
    now = datetime.now()
    stale = [jid for jid, job in _backtest_jobs.items()
             if (now - job.get("_created", now)).total_seconds() > _JOB_TTL_SEC
             and job.get("status") in ("done", "error")]
    for jid in stale:
        del _backtest_jobs[jid]


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
    from src.common.costs import US_STOCKS, HK_STOCKS, CRYPTO, ZERO
    from datetime import timedelta
    import os

    job = _backtest_jobs[job_id]
    try:
        capital = params["capital"]
        cost_models = {"us_stocks": US_STOCKS, "hk_stocks": HK_STOCKS, "crypto": CRYPTO, "zero": ZERO}
        costs = cost_models.get(params.get("cost_model", "us_stocks"), US_STOCKS)

        # Load news
        news_src = params.get("news_source", "sample")
        if news_src == "mongodb":
            try:
                client = get_mongo_client()
                docs = list(client["EonTradingDB"]["news"].find({}, {"_id": 0}).sort("timestamp", 1).limit(200))
                news_list = [{"date": d.get("timestamp", ""), "headline": d.get("headline", "")} for d in docs if d.get("headline")]
                if not news_list:
                    job["status"] = "error"
                    job["error"] = "No news found in MongoDB"
                    return
            except Exception as e:
                job["status"] = "error"
                job["error"] = f"MongoDB error: {e}"
                return
        else:
            news_list = SAMPLE_NEWS

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

        broker = PaperBroker(initial_cash=capital, cost_model=costs)
        monitor = PriceMonitor(bus, None, logic, interval_sec=0)
        trader = SentimentTrader(bus, logic=logic, broker=broker, price_monitor=monitor)
        analyzer_svc = AnalyzerService(bus, analyzer=anlzr, get_positions=lambda: trader.holdings)
        executor = TradeExecutor(bus, broker)

        fills = []

        async def on_fill(msg):
            fills.append(msg)
            action = msg.get("action", "")
            symbol = msg.get("symbol", "")
            status = "✅" if msg.get("success") else "❌"
            job["log"].append(f"{status} {action.upper()} {symbol} — {msg.get('reason', '')}")

        await bus.subscribe(CHANNEL_FILL, on_fill)
        await analyzer_svc.start()
        await trader.start()
        await executor.start()

        equity = []
        prev_date = None
        sl_check_hours = params["sl_check_hours"]

        job["log"].append(f"📊 {len(news_list)} news events, cost model: {params.get('cost_model', 'us_stocks')}")

        for i, doc in enumerate(news_list):
            curr = datetime.fromisoformat(doc["date"])

            if prev_date and monitor._states:
                check_time = prev_date + timedelta(hours=sl_check_hours)
                while check_time < curr:
                    sold = await monitor.check_once(broker, as_of=check_time.isoformat())
                    await asyncio.sleep(0.05)
                    if sold:
                        job["log"].append(f"⏰ SL/TP check @ {check_time.strftime('%Y-%m-%d %H:%M')} — sold {', '.join(sold)}")
                    check_time += timedelta(hours=sl_check_hours)

            prev_date = curr
            await monitor.check_once(broker, as_of=doc["date"])
            await asyncio.sleep(0.05)

            job["log"].append(f"📅 {doc['date'][:16]} — {doc['headline'][:70]}")

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

            job["progress"] = round((i + 1) / len(news_list) * 100)

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
        last_date = news_list[-1]["date"]
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
        job["error"] = f"{type(e).__name__}: {e}"


@app.post("/api/live-backtest", dependencies=[Depends(_check_api_key)])
async def start_live_backtest(
    capital: float = Query(default=70000, ge=100, le=100_000_000),
    threshold: float = Query(default=0.4, ge=0, le=1),
    max_allocation: float = Query(default=0.2, ge=0.01, le=1),
    stop_loss: float = Query(default=0.05, ge=0.001, le=0.5),
    take_profit: float = Query(default=0.10, ge=0.001, le=5.0),
    max_hold_days: int = Query(default=30, ge=1, le=365),
    sl_check_hours: int = Query(default=24, ge=1, le=720),
    analyzer: str = "keyword",
    cost_model: str = "us_stocks",
    news_source: str = "sample",
):
    """Start a live pipeline backtest as a background task."""
    import uuid
    _cleanup_stale_jobs()
    job_id = str(uuid.uuid4())[:8]
    _backtest_jobs[job_id] = {"status": "running", "progress": 0, "log": [], "_created": datetime.now()}
    params = dict(capital=capital, threshold=threshold, max_allocation=max_allocation,
                  stop_loss=stop_loss, take_profit=take_profit, max_hold_days=max_hold_days,
                  sl_check_hours=sl_check_hours, analyzer=analyzer,
                  cost_model=cost_model, news_source=news_source)
    asyncio.create_task(_run_live_backtest(job_id, params))
    return {"job_id": job_id, "status": "running"}


@app.get("/api/live-backtest/{job_id}")
def get_live_backtest(job_id: str):
    """Poll backtest status/result."""
    _cleanup_stale_jobs()
    job = _backtest_jobs.get(job_id)
    if not job:
        return {"status": "not_found"}
    if job["status"] == "done":
        result = job["result"]
        del _backtest_jobs[job_id]  # cleanup
        return {"status": "done", **result}
    return {"status": job["status"], "progress": job.get("progress", 0), "log": job.get("log", [])}


@app.get("/api/news")
def news(limit: int = 100):
    try:
        client = get_mongo_client()
        col = client["EonTradingDB"]["news"]
        docs = list(col.find({}, {"_id": 0}).sort("collected_at", -1).limit(limit))
        return docs
    except Exception as e:
        logger.warning("News fetch error: %s", e)
        return {"error": f"MongoDB unavailable: {e}", "fallback": True, "articles": SAMPLE_NEWS}


@app.get("/api/news/count")
def news_count():
    try:
        client = get_mongo_client()
        col = client["EonTradingDB"]["news"]
        return {"count": col.count_documents({})}
    except Exception:
        logger.warning("Failed to count news", exc_info=True)
        return {"count": 0}
