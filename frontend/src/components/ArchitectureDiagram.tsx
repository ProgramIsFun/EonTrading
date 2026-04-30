// Colors: process=blue, internal=green, service=amber, source=neutral
const PROCESS = "#1a2a4a";
const INTERNAL = "#1a3a2a";
const SERVICE = "#3a2a1a";
const SOURCE = "#2a2a3a";
const DISABLED = "#1a1a1a";
const STATE = "#2a1a2a";

const borders: Record<string, string> = {
  [PROCESS]: "#818cf844",
  [INTERNAL]: "#22c55e44",
  [SERVICE]: "#f59e0b44",
  [SOURCE]: "#44444466",
  [DISABLED]: "#33333344",
  [STATE]: "#c084fc44",
};

const boxStyle = (color: string) => ({
  background: color,
  borderRadius: 8,
  padding: "8px 14px",
  fontSize: 12,
  color: color === DISABLED ? "#555" : "#e0e0e0",
  textAlign: "center" as const,
  minWidth: 100,
  border: `1px solid ${borders[color] || "#333"}`,
  ...(color === DISABLED ? { borderStyle: "dashed" as const } : {}),
});

const tag = (text: string, bg: string, fg: string) => (
  <span style={{ fontSize: 9, background: bg, color: fg, padding: "1px 5px", borderRadius: 3 }}>{text}</span>
);
const processTag = (t?: string) => tag(t || "process", "#818cf822", "#818cf8");
const internalTag = () => tag("internal", "#22c55e22", "#22c55e");
const serviceTag = () => tag("service", "#f59e0b22", "#f59e0b");
const stateTag = () => tag("state", "#c084fc22", "#c084fc");
const envReq = (v: string) => (
  <div style={{ fontSize: 8, fontFamily: "monospace", color: "#ef4444", marginTop: 1 }}>● {v}</div>
);
const envOpt = (v: string) => (
  <div style={{ fontSize: 8, fontFamily: "monospace", color: "#22c55e", marginTop: 1 }}>○ {v}</div>
);
const pathTag = (p: string) => (
  <div style={{ fontSize: 9, color: "#555", fontFamily: "monospace", marginTop: 2 }}>{p}</div>
);

const mongoBox = (collection: string, detail: string) => (
  <div style={boxStyle(SERVICE)}>
    <div style={{ fontWeight: 600 }}>MongoDB</div>
    <div style={{ fontSize: 10, color: "#f59e0b" }}>{collection}</div>
    <div style={{ fontSize: 9, color: "#888" }}>{detail}</div>
    {serviceTag()}
  </div>
);

const arrow = { color: "#555", fontSize: 18 };
const arrowDown = { color: "#555", fontSize: 14, textAlign: "center" as const, padding: "2px 0" };
const label = (text: string) => <span style={{ fontSize: 10, color: "#666" }}>{text}</span>;

const sectionTitle = (text: string, color: string) => (
  <div style={{ fontSize: 12, color, marginBottom: 8, fontWeight: 600 }}>{text}</div>
);

const section = { marginBottom: 24, borderBottom: "1px solid #333", paddingBottom: 20 };

import { useState, useEffect } from "react";

export default function ArchitectureDiagram() {
  const [redisUp, setRedisUp] = useState<boolean | null>(null);

  useEffect(() => {
    const check = () =>
      fetch("/api/docker/status")
        .then((r) => r.json())
        .then((d) => {
          const redis = (d.containers || []).find((c: { name: string; state: string }) => c.name === "redis");
          setRedisUp(redis ? redis.state === "running" : false);
        })
        .catch(() => setRedisUp(null));
    check();
    const id = setInterval(check, 15000);
    return () => clearInterval(id);
  }, []);
  return (
    <div style={{ background: "#1e1e2e", borderRadius: 8, padding: 24 }}>
      <div style={{ fontSize: 14, color: "#888", marginBottom: 4 }}>System Architecture</div>

      {/* Summary */}
      <div style={{ fontSize: 12, color: "#ccc", marginBottom: 16, lineHeight: 1.6 }}>
        News comes in → gets scored for sentiment → triggers trades → broker confirms fill.
        <span style={{ color: "#888" }}> Everything flows through event channels, whether in one process or distributed across many.</span>
      </div>

      {/* Core Channel Flow */}
      <div style={{ ...section }}>
        {sectionTitle("Core Pipeline", "#818cf8")}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 12, flexWrap: "wrap", padding: "12px 0" }}>
          {[
            { ch: "news", desc: "raw headlines" },
            { ch: "sentiment", desc: "scored signals" },
            { ch: "trade", desc: "buy/sell orders" },
            { ch: "fill", desc: "broker confirmation" },
          ].map((c, i) => (
            <div key={c.ch} style={{ display: "flex", alignItems: "center", gap: 12 }}>
              {i > 0 && <span style={{ color: "#818cf8", fontSize: 20 }}>→</span>}
              <div style={{ textAlign: "center" }}>
                <code style={{ fontSize: 14, color: "#818cf8", fontWeight: 600 }}>[{c.ch}]</code>
                <div style={{ fontSize: 9, color: "#666" }}>{c.desc}</div>
              </div>
            </div>
          ))}
        </div>
        <div style={{ fontSize: 10, color: "#666", textAlign: "center" }}>
          Same channels whether LocalEventBus (in-memory) or RedisStreamBus (persistent message queue).
        </div>
      </div>

      {/* Live Pipeline */}
      <div style={section}>
        {sectionTitle("Live Trading Pipeline", "#818cf8")}

        {/* Host: API Server */}
        <div style={{ background: "#1a2a1a", borderRadius: 8, padding: 10, marginBottom: 12, border: "1px dashed #22c55e44" }}>
          <div style={{ fontSize: 10, color: "#22c55e", marginBottom: 6 }}>🖥 Host (native Python — not in Docker)</div>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <div style={boxStyle(PROCESS)}>
              <div style={{ fontWeight: 600 }}>FastAPI Server</div>
              <div style={{ fontSize: 10, color: "#888" }}>dashboard + backtest + docker control</div>
              {processTag("uvicorn")}
              {pathTag("src/api/server.py")}
              {envReq("REDIS_HOST=localhost")}
              <div style={{ fontSize: 8, color: "#555" }}>ping/pong + price cache via Redis</div>
            </div>
            <div style={boxStyle(INTERNAL)}>
              <div style={{ fontWeight: 600 }}>Reconciliation</div>
              <div style={{ fontSize: 10, color: "#888" }}>system vs broker check</div>
              <div style={{ fontSize: 9, color: "#666" }}>on startup + GET /api/reconcile</div>
              {pathTag("src/common/reconcile.py")}
              <div style={{ fontSize: 8, color: "#ef4444", marginTop: 2 }}>live only — not used in replay</div>
            </div>
            <span style={{ fontSize: 10, color: "#666" }}>→ manages containers, pings via Redis →</span>
          </div>
        </div>

        {/* Docker boundary */}
        <div style={{ background: "#1a1a2e", borderRadius: 8, padding: 12, border: "2px dashed #818cf844", position: "relative" as const }}>
          <div style={{ fontSize: 10, color: "#818cf8", marginBottom: 8 }}>
            🐳 Docker containers
            <span style={{ color: "#555", marginLeft: 8 }}>REDIS_HOST=redis (Docker DNS)</span>
          </div>

          {/* Redis */}
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 10 }}>
            <div style={{
              ...boxStyle(SERVICE),
              border: `1px solid ${redisUp ? "#22c55e66" : redisUp === false ? "#ef444466" : "#33333366"}`,
              position: "relative" as const,
              overflow: "hidden" as const,
            }}>
              {redisUp && (
                <div style={{
                  position: "absolute", top: 4, right: 8,
                  width: 8, height: 8, borderRadius: "50%",
                  background: "#22c55e",
                  animation: "pulse 2s ease-in-out infinite",
                }} />
              )}
              <style>{`@keyframes pulse { 0%, 100% { opacity: 1; box-shadow: 0 0 0 0 #22c55e88; } 50% { opacity: 0.6; box-shadow: 0 0 8px 4px #22c55e44; } }`}</style>
              <div style={{ fontWeight: 600 }}>
                {redisUp === true ? "🟢" : redisUp === false ? "🔴" : "⚫"} Redis
              </div>
              <div style={{ fontSize: 10, color: "#888" }}>streams (pipeline) + pub/sub (ping/pong) + price cache</div>
              {serviceTag()}
              <div style={{ fontSize: 8, color: "#555", marginTop: 2 }}>port 6379 → host</div>
              <div style={{ fontSize: 8, color: redisUp ? "#22c55e" : "#555", marginTop: 2, fontWeight: redisUp ? 600 : 400 }}>
                {redisUp === true ? "● running" : redisUp === false ? "● stopped" : "● unknown"}
              </div>
            </div>
            <span style={{ fontSize: 9, color: "#555" }}>streams: [news] [sentiment] [trade] [fill] · pub/sub: [ping] [pong]</span>
          </div>

          {/* Row 1: Sources → Watcher → [news] → Analyzer → [sentiment] */}
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <div style={{ display: "flex", gap: 6 }}>
              {[
                { name: "NewsAPI", path: "src/data/news/newsapi_source.py", env: "NEWSAPI_KEY" },
                { name: "Finnhub", path: "src/data/news/finnhub_source.py", env: "FINNHUB_KEY" },
                { name: "RSS", path: "src/data/news/rss_source.py", env: null },
                { name: "Reddit", path: "src/data/news/reddit_source.py", env: null },
              ].map((s) => (
                <div key={s.name} style={boxStyle(SOURCE)}>
                  {s.name}
                  {pathTag(s.path)}
                  {s.env ? envOpt(s.env) : <div style={{ fontSize: 8, color: "#555", marginTop: 1 }}>always on</div>}
                </div>
              ))}
              <div style={boxStyle(SOURCE)}>
                Twitter/X
                {pathTag("src/data/news/twitter_source.py")}
                {envOpt("TWITTER_BEARER_TOKEN")}
              </div>
            </div>
            <span style={arrow}>→</span>
            <div style={boxStyle(INTERNAL)}>
              <div style={{ fontWeight: 600 }}>NewsWatcher</div>
              <div style={{ fontSize: 10, color: "#888" }}>uses NewsPoller</div>
              {internalTag()}
              {pathTag("src/live/news_watcher.py")}
              {pathTag("src/common/news_poller.py")}
            </div>
            <span style={arrow}>→</span>
            {label("[news]")}
            <span style={arrow}>→</span>
            <div>
              <div style={boxStyle(INTERNAL)}>
                <div style={{ fontWeight: 600 }}>AnalyzerService</div>
                <div style={{ fontSize: 10, color: "#888" }}>Keyword / LLM + positions</div>
                {internalTag()}
                {pathTag("src/live/analyzer_service.py")}
                {pathTag("src/strategies/sentiment.py")}
                {envOpt("OPENAI_API_KEY")}
                <div style={{ fontSize: 8, color: "#555" }}>default: keyword (free)</div>
              </div>
              <div style={arrowDown}>↑ reads</div>
              {mongoBox("positions", "get open positions")}
            </div>
            <span style={arrow}>→</span>
            {label("[sentiment]")}
          </div>

          {/* Row 2: → Trader → [trade] → Executor/Broker → [fill] → back to Trader */}
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
            <span style={arrow}>→</span>
            <div style={boxStyle(INTERNAL)}>
              <div style={{ fontWeight: 600 }}>SentimentTrader</div>
              <div style={{ fontSize: 10, color: "#818cf8" }}>TradingLogic ↗</div>
              <div style={{ fontSize: 9, color: "#888" }}>tracks pending orders</div>
              {internalTag()}
              {pathTag("src/live/sentiment_trader.py")}
            </div>
            <span style={arrow}>→</span>
            {label("[trade]")}
            <span style={arrow}>→</span>
            <div style={boxStyle(INTERNAL)}>
              <div style={{ fontWeight: 600 }}>Executor</div>
              {internalTag()}
              {pathTag("src/live/brokers/broker.py")}
            </div>
            <span style={arrow}>→</span>
            <div style={boxStyle(PROCESS)}>
              <div style={{ fontWeight: 600 }}>Broker</div>
              <div style={{ fontSize: 10, color: "#888" }}>Log / Futu / IBKR / Alpaca</div>
              <div style={{ fontSize: 9, color: "#666" }}>each confirms in its own way</div>
              <div style={{ fontSize: 9, color: "#555", marginTop: 2 }}>polling · callback · instant</div>
              {envOpt("BROKER")}
              {envOpt("ALPACA_API_KEY")}
              {envOpt("ALPACA_SECRET_KEY")}
              {envOpt("FUTU_LIVE / FUTU_REAL")}
              <div style={{ fontSize: 8, color: "#555" }}>default: PaperBroker (dry run)</div>
            </div>
            <span style={arrow}>→</span>
            {label("[fill]")}
            <span style={arrow}>→</span>
            <div>
              <div style={{ ...boxStyle(INTERNAL), border: "1px solid #22c55e66" }}>
                <div style={{ fontWeight: 600 }}>SentimentTrader</div>
                <div style={{ fontSize: 10, color: "#22c55e" }}>✅ filled → persist</div>
                <div style={{ fontSize: 10, color: "#ef4444" }}>❌ rejected → rollback</div>
              </div>
              <div style={arrowDown}>↓ on fill</div>
              {mongoBox("positions", "open/close position")}
            </div>
          </div>

          {/* PriceMonitor */}
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 12 }}>
            <div style={boxStyle(INTERNAL)}>
              <div style={{ fontWeight: 600 }}>PriceMonitor</div>
              <div style={{ fontSize: 10, color: "#888" }}>self-managed SL/TP</div>
              <div style={{ fontSize: 9, color: "#666" }}>polls prices → publishes sell to [trade]</div>
              {internalTag()}
              {pathTag("src/live/price_monitor.py")}
              <div style={{ fontSize: 8, color: "#555" }}>live: yfinance (latest prices)</div>
            </div>
            <span style={arrow}>→</span>
            {label("[trade]")}
            <span style={{ fontSize: 10, color: "#666" }}>same flow as sentiment sells — you control risk, not the broker</span>
          </div>
        </div>

        <div style={{ fontSize: 10, color: "#666", marginTop: 10 }}>
          Trader updates in-memory first, marks order as pending, then waits for <code style={{ color: "#818cf8" }}>[fill]</code> from broker.
          MongoDB is only written after broker confirms. If rejected, in-memory state rolls back.
        </div>

        {/* Replay mode */}
        <div style={{ background: "#1a2a2a", borderRadius: 6, padding: 10, marginTop: 12, border: "1px dashed #22c55e44" }}>
          <div style={{ fontSize: 11, color: "#22c55e", fontWeight: 600, marginBottom: 4 }}>♻️ Replay Mode (backtest via live pipeline)</div>
          <div style={{ fontSize: 10, color: "#888" }}>
            Same pipeline, same code — but fed with historical news from MongoDB.
            Timestamps flow with events. Prices from ClickHouse (<code style={{ color: "#818cf8" }}>PRICE_SOURCE=clickhouse</code>) or yfinance.
          </div>
          <div style={{ fontSize: 9, color: "#666", marginTop: 4 }}>
            {envOpt("PRICE_SOURCE")} <span>clickhouse (fast, local) or yfinance (default, API)</span>
          </div>
          <div style={{ fontSize: 9, color: "#666" }}>
            {envOpt("SL_CHECK_HOURS")} <span>24 (default) or 1 for hourly SL/TP checks</span>
          </div>
          <code style={{ fontSize: 9, color: "#818cf8", display: "block", marginTop: 4 }}>
            python -m src.live.replay --start 2025-01-01 --end 2025-06-01
          </code>
          <div style={{ fontSize: 9, color: "#666", marginTop: 6 }}>
            <div style={{ color: "#ccc", marginBottom: 2 }}>Backtest scripts:</div>
            <code style={{ fontSize: 8, color: "#818cf8", display: "block" }}>
              PRICE_SOURCE=clickhouse python3 scripts/backtest/live_pipeline_backtest.py
            </code>
            <div style={{ fontSize: 8, color: "#555" }}>↑ keyword analyzer</div>
            <code style={{ fontSize: 8, color: "#818cf8", display: "block", marginTop: 2 }}>
              PRICE_SOURCE=clickhouse SL_CHECK_HOURS=1 python3 scripts/backtest/live_pipeline_llm_backtest.py
            </code>
            <div style={{ fontSize: 8, color: "#555" }}>↑ pre-scored LLM sentiment, hourly SL/TP</div>
          </div>

          {/* Live vs Replay differences */}
          <table style={{ fontSize: 9, color: "#888", borderCollapse: "collapse", width: "100%", marginTop: 8 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid #333", color: "#ccc" }}>
                <th style={{ textAlign: "left", padding: "3px 6px" }}>Aspect</th>
                <th style={{ textAlign: "left", padding: "3px 6px" }}>🔴 Live (real money)</th>
                <th style={{ textAlign: "left", padding: "3px 6px" }}>♻️ Replay (backtest)</th>
              </tr>
            </thead>
            <tbody>
              {[
                ["News source", "RSS, Reddit, NewsAPI, Finnhub, Twitter", "Historical from MongoDB or hardcoded"],
                ["Prices", "Latest market price (yfinance)", "Historical at event timestamp (ClickHouse/yfinance)"],
                ["Broker", "Futu / IBKR / Alpaca (real orders)", "PaperBroker (simulated, instant fill)"],
                ["Fill confirmation", "Async — broker polls/callback", "Instant — PaperBroker always succeeds"],
                ["SL/TP monitoring", "PriceMonitor polls every 60s (live prices)", "Stepped through historical timestamps between events"],
                ["Transaction costs", "Real broker fees", "CostModel (US_STOCKS: 0.05% slippage)"],
                ["Reconciliation", "Compares system vs broker on startup", "Not used"],
                ["Execution", "Distributed (Docker + Redis)", "Single process (LocalEventBus)"],
                ["NewsWatcher", "Active — polls sources every 120s", "Not used — events injected directly"],
                ["Positions", "Persisted to MongoDB", "Persisted to MongoDB (cleared before run)"],
              ].map(([aspect, live, replay]) => (
                <tr key={aspect} style={{ borderBottom: "1px solid #222" }}>
                  <td style={{ padding: "2px 6px", color: "#ccc" }}>{aspect}</td>
                  <td style={{ padding: "2px 6px" }}>{live}</td>
                  <td style={{ padding: "2px 6px" }}>{replay}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* News Data Pipeline */}
      <div style={section}>
        {sectionTitle("News Data Pipeline", "#f472b6")}
        <div style={{ fontSize: 10, color: "#888", marginBottom: 8 }}>
          Independent from the live pipeline. Uses the same RSS/Reddit sources but stores to MongoDB for backtesting and historical analysis.
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
          <span style={{ fontSize: 10, color: "#888", width: 55 }}>Live:</span>
          <div style={{ display: "flex", gap: 6 }}>
            {["RSS", "Reddit"].map((s) => (
              <div key={s} style={boxStyle(SOURCE)}>{s}</div>
            ))}
          </div>
          <span style={arrow}>→</span>
          <div style={boxStyle(PROCESS)}>
            <div style={{ fontWeight: 600 }}>collect_news.py</div>
            <div style={{ fontSize: 10, color: "#888" }}>poll every 5min</div>
            {processTag()}
            {pathTag("scripts/collect_news.py")}
          </div>
          <span style={arrow}>→</span>
          {mongoBox("news", "dedup by URL")}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span style={{ fontSize: 10, color: "#888", width: 55 }}>Backfill:</span>
          <div style={{ display: "flex", gap: 6 }}>
            {["Finnhub", "NewsAPI"].map((s) => (
              <div key={s} style={boxStyle(SOURCE)}>{s}</div>
            ))}
          </div>
          <span style={arrow}>→</span>
          <div style={boxStyle(PROCESS)}>
            <div style={{ fontWeight: 600 }}>backfill_news.py</div>
            <div style={{ fontSize: 10, color: "#888" }}>historical, per symbol</div>
            {processTag("one-off")}
            {pathTag("scripts/backfill_news.py")}
          </div>
          <span style={arrow}>→</span>
          {mongoBox("news", "backfilled: true")}
        </div>
      </div>

      {/* Backtest Pipeline (Legacy) */}
      <div style={{ ...section, opacity: 0.6 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
          {sectionTitle("Backtest Pipeline", "#22c55e")}
          <span style={{ fontSize: 9, background: "#55555522", color: "#888", padding: "1px 6px", borderRadius: 3 }}>legacy — use Replay Mode instead</span>
        </div>
        <div style={{ fontSize: 10, color: "#666", marginBottom: 8 }}>
          Separate batch pipeline. Useful for quick parameter sweeps and equity curves, but uses different execution
          mechanics than live (simulated hourly candles vs real event flow). For accurate results, use Replay Mode above.
        </div>
        {processTag("runs inside FastAPI")}
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
          {mongoBox("ohlcv", "price candles")}
          <span style={arrow}>→</span>
          {mongoBox("news", "real articles")}
          <span style={{ ...arrow, color: "#888", fontSize: 11 }}>or synthetic</span>
          <span style={arrow}>→</span>
          <div style={boxStyle(INTERNAL)}>
            <div style={{ fontWeight: 600 }}>Analyzer</div>
            {internalTag()}
            {pathTag("src/strategies/sentiment.py")}
          </div>
          <span style={arrow}>→</span>
          <div style={boxStyle(INTERNAL)}>
            <div style={{ fontWeight: 600 }}>Backtest Engine</div>
            <div style={{ fontSize: 10, color: "#818cf8" }}>TradingLogic ↗</div>
            {internalTag()}
            {pathTag("src/backtest/portfolio_backtest.py")}
            {pathTag("src/backtest/engine.py")}
          </div>
        </div>
      </div>

      {/* Dashboard */}
      <div style={section}>
        {sectionTitle("Dashboard", "#f59e0b")}
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <div style={boxStyle(PROCESS)}>
            <div style={{ fontWeight: 600 }}>React + Vite</div>
            <div style={{ fontSize: 10, color: "#888" }}>charts, controls</div>
            {processTag("npm run dev")}
            {pathTag("frontend/")}
          </div>
          <span style={arrow}>→ HTTP →</span>
          <div style={boxStyle(PROCESS)}>
            <div style={{ fontWeight: 600 }}>FastAPI</div>
            <div style={{ fontSize: 10, color: "#888" }}>/api/backtest</div>
            {processTag("uvicorn")}
            {pathTag("src/api/server.py")}
          </div>
          <span style={arrow}>→</span>
          <div style={boxStyle(INTERNAL)}>
            <div style={{ fontWeight: 600 }}>Backtest Engine</div>
            {internalTag()}
          </div>
        </div>
        <div style={{ fontSize: 10, color: "#666", marginTop: 6 }}>
          FastAPI serves both the dashboard API and runs backtests — same server process.
        </div>
      </div>

      {/* Shared: TradingLogic */}
      <div style={section}>
        {sectionTitle("Shared: TradingLogic", "#818cf8")}
        {pathTag("src/common/trading_logic.py")}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", fontSize: 11, color: "#888", marginTop: 6 }}>
          {["should_buy()", "should_sell_on_sentiment()", "check_stop_loss()", "check_take_profit()", "update_peak()"].map((m) => (
            <span key={m} style={{ background: "#2a2a3e", padding: "4px 8px", borderRadius: 4, fontFamily: "monospace" }}>{m}</span>
          ))}
        </div>
        <div style={{ fontSize: 10, color: "#666", marginTop: 6 }}>
          Used by: <code style={{ color: "#22c55e" }}>SentimentTrader</code> (live) and <code style={{ color: "#22c55e" }}>Backtest Engine</code> (backtest) — same logic, both modes.
        </div>
        <div style={{ fontSize: 11, color: "#666", marginTop: 4 }}>
          Cash only — no margin, no leverage, no short selling. Max loss = initial capital.
        </div>
      </div>

      {/* Ephemeral State */}
      <div style={section}>
        {sectionTitle("Ephemeral State (in-memory, resets on restart)", "#c084fc")}
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <div style={boxStyle(STATE)}>
            <div style={{ fontWeight: 600 }}>Trader holdings</div>
            <div style={{ fontSize: 10, color: "#888" }}>in-memory dict</div>
            {stateTag()}
            <div style={{ fontSize: 9, color: "#666", marginTop: 2 }}>restored from MongoDB on startup</div>
          </div>
          <div style={boxStyle(STATE)}>
            <div style={{ fontWeight: 600 }}>Pending orders</div>
            <div style={{ fontSize: 10, color: "#888" }}>symbol → buy/sell</div>
            {stateTag()}
            <div style={{ fontSize: 9, color: "#666", marginTop: 2 }}>awaiting [fill] from broker</div>
          </div>
          <div style={boxStyle(STATE)}>
            <div style={{ fontWeight: 600 }}>Source _seen sets</div>
            <div style={{ fontSize: 10, color: "#888" }}>in-memory per source</div>
            {stateTag()}
            <div style={{ fontSize: 9, color: "#666", marginTop: 2 }}>dedup resets on restart</div>
          </div>
        </div>
      </div>

      {/* MongoDB summary */}
      <div style={{ background: "#1a1a2e", borderRadius: 8, padding: 12, marginBottom: 20, border: `1px solid ${borders[SERVICE]}` }}>
        {sectionTitle("MongoDB Collections (EonTradingDB)", "#f59e0b")}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 10, color: "#888" }}>
          {[
            { name: "news", desc: "Articles — written by collect/backfill scripts, read by backtest" },
            { name: "ohlcv", desc: "Price candles — written by ingest/migrations, read by backtest" },
            { name: "positions", desc: "Open trades — written on broker fill, read by Analyzer" },
            { name: "trades", desc: "Confirmed trade history — written on broker fill, read by API" },
            { name: "replay_trades", desc: "Replay backtest trades — written by replay mode" },
            { name: "symbols", desc: "Stock list — written by update_sp500.py, read by API & scripts" },
            { name: "seen_urls", desc: "Dedup — written/read by NewsPoller, survives restarts" },
          ].map((c) => (
            <div key={c.name} style={{ display: "flex", gap: 6, alignItems: "baseline" }}>
              <code style={{ color: "#f59e0b", fontWeight: 600, minWidth: 65 }}>{c.name}</code>
              <span>{c.desc}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Deployment Modes */}
      <div style={{ background: "#1a1a2e", borderRadius: 8, padding: 12, marginBottom: 20, border: "1px solid #333" }}>
        {sectionTitle("Deployment Modes", "#818cf8")}
        <div style={{ display: "flex", gap: 24, fontSize: 11, color: "#ccc" }}>
          <div>
            <div style={{ fontWeight: 600, marginBottom: 4 }}>🟢 Single Process (default)</div>
            <div style={{ color: "#888" }}>All components in one Python process.</div>
            <div style={{ color: "#888" }}>Uses LocalEventBus (in-memory).</div>
            <div style={{ color: "#6ee7b7", fontSize: 10, marginTop: 2 }}>Best for: dev, replay/backtest, debugging</div>
            <code style={{ fontSize: 10, color: "#818cf8" }}>python3 -m src.live.news_trader</code>
          </div>
          <div>
            <div style={{ fontWeight: 600, marginBottom: 4 }}>🔵 Distributed (separate processes)</div>
            <div style={{ color: "#888" }}>Each component runs independently.</div>
            <div style={{ color: "#888" }}>Uses RedisStreamBus (persistent message queue).</div>
            <div style={{ color: "#93c5fd", fontSize: 10, marginTop: 2 }}>Best for: production, scaling, per-component restarts</div>
            {envReq("REDIS_HOST")}
            <div style={{ display: "flex", flexDirection: "column", gap: 2, marginTop: 4 }}>
              <code style={{ fontSize: 10, color: "#818cf8" }}>python3 -m src.live.runners.run_watcher</code>
              <code style={{ fontSize: 10, color: "#818cf8" }}>python3 -m src.live.runners.run_analyzer</code>
              <code style={{ fontSize: 10, color: "#818cf8" }}>python3 -m src.live.runners.run_trader</code>
              <code style={{ fontSize: 10, color: "#818cf8" }}>python3 -m src.live.runners.run_executor</code>
            </div>
          </div>
        </div>
      </div>

      {/* Env var legend */}
      <div style={{ background: "#1a1a2e", borderRadius: 8, padding: 12, border: "1px solid #333" }}>
        {sectionTitle("Environment Variables", "#f59e0b")}
        <div style={{ fontSize: 10, color: "#888", marginBottom: 6 }}>
          Env vars are shown on each component above. All components require MongoDB:
        </div>
        <div style={{ display: "flex", gap: 16, fontSize: 10, flexWrap: "wrap" }}>
          <div>
            {envReq("MONGODB_URI")}
            {envReq("MONGODB_USER")}
            {envReq("MONGODB_PASS")}
            {envReq("MONGODB_CLUSTERNAME")}
          </div>
          <div style={{ color: "#666", fontSize: 9, alignSelf: "center" }}>
            <div><span style={{ color: "#ef4444" }}>●</span> = required</div>
            <div><span style={{ color: "#22c55e" }}>○</span> = optional (enables feature)</div>
            <div style={{ marginTop: 4 }}>RSS + Reddit are always on, no key needed.</div>
            <div>Default broker: PaperBroker (dry run).</div>
            <div>Default analyzer: Keyword (free).</div>
          </div>
        </div>
      </div>

      {/* Legend */}
      <div style={{ display: "flex", gap: 12, marginTop: 16, fontSize: 11, color: "#888", flexWrap: "wrap", alignItems: "center" }}>
        {processTag()} <span>standalone process</span>
        {internalTag()} <span>runs inside parent process</span>
        {serviceTag()} <span>external service / MongoDB</span>
        {stateTag()} <span>ephemeral state</span>
      </div>
    </div>
  );
}
