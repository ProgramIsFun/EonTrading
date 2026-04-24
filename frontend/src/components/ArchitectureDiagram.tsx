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
const disabledTag = () => tag("not wired", "#55555522", "#555");
const stateTag = () => tag("state", "#c084fc22", "#c084fc");
const pathTag = (p: string) => (
  <div style={{ fontSize: 9, color: "#555", fontFamily: "monospace", marginTop: 2 }}>{p}</div>
);

const arrow = { color: "#555", fontSize: 18 };
const label = (text: string) => <span style={{ fontSize: 10, color: "#666" }}>{text}</span>;

const sectionTitle = (text: string, color: string) => (
  <div style={{ fontSize: 12, color, marginBottom: 8, fontWeight: 600 }}>{text}</div>
);

const section = { marginBottom: 24, borderBottom: "1px solid #333", paddingBottom: 20 };

export default function ArchitectureDiagram() {
  return (
    <div style={{ background: "#1e1e2e", borderRadius: 8, padding: 24 }}>
      <div style={{ fontSize: 14, color: "#888", marginBottom: 4 }}>System Architecture</div>

      {/* Summary */}
      <div style={{ fontSize: 12, color: "#ccc", marginBottom: 16, lineHeight: 1.6 }}>
        News comes in → gets scored for sentiment → triggers trades.
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
          Same channels whether LocalEventBus (in-memory) or RedisEventBus (cross-process).
        </div>
      </div>

      {/* Live Pipeline */}
      <div style={section}>
        {sectionTitle("Live Trading Pipeline", "#818cf8")}
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <div style={{ display: "flex", gap: 6 }}>
            {[
              { name: "NewsAPI", path: "src/data/news/newsapi_source.py" },
              { name: "Finnhub", path: "src/data/news/finnhub_source.py" },
              { name: "RSS", path: "src/data/news/rss_source.py" },
              { name: "Reddit", path: "src/data/news/reddit_source.py" },
            ].map((s) => (
              <div key={s.name} style={boxStyle(SOURCE)}>
                {s.name}
                {pathTag(s.path)}
              </div>
            ))}
            <div style={boxStyle(DISABLED)}>
              Twitter/X
              {disabledTag()}
              {pathTag("src/data/news/twitter_source.py")}
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
          <div style={boxStyle(INTERNAL)}>
            <div style={{ fontWeight: 600 }}>AnalyzerService</div>
            <div style={{ fontSize: 10, color: "#888" }}>Keyword / LLM + positions</div>
            {internalTag()}
            {pathTag("src/live/analyzer_service.py")}
            {pathTag("src/strategies/sentiment.py")}
          </div>
          <span style={arrow}>→</span>
          {label("[sentiment]")}
          <span style={arrow}>→</span>
          <div style={boxStyle(INTERNAL)}>
            <div style={{ fontWeight: 600 }}>SentimentTrader</div>
            <div style={{ fontSize: 10, color: "#818cf8" }}>TradingLogic ↗</div>
            {internalTag()}
            {pathTag("src/live/sentiment_trader.py")}
          </div>
          <span style={arrow}>→</span>
          {label("[trade]")}
          <span style={arrow}>→</span>
          <div style={boxStyle(INTERNAL)}>
            <div style={{ fontWeight: 600 }}>Executor</div>
            <div style={{ fontSize: 10, color: "#888" }}>Log / Futu</div>
            {internalTag()}
            {pathTag("src/live/brokers/broker.py")}
          </div>
        </div>
        <div style={{ fontSize: 10, color: "#888", marginTop: 8 }}>
          AnalyzerService queries <code style={{ color: "#818cf8" }}>get_positions()</code> from Trader for portfolio-aware LLM scoring. Broker exposes <code style={{ color: "#818cf8" }}>execute(trade)</code> + <code style={{ color: "#818cf8" }}>get_positions()</code>.
        </div>
        <div style={{ fontSize: 10, color: "#666", marginTop: 4 }}>
          Live pipeline is real-time via event bus — it does not read from MongoDB.
        </div>
      </div>

      {/* News Data Pipeline */}
      <div style={section}>
        {sectionTitle("News Data Pipeline → MongoDB (EonTradingDB.news)", "#f472b6")}
        <div style={{ fontSize: 10, color: "#888", marginBottom: 8 }}>
          Independent from the live pipeline. Uses the same RSS/Reddit sources but stores to MongoDB for backtesting and historical analysis.
          The live pipeline streams through the event bus in real-time; this one builds a persistent dataset.
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
          <div style={boxStyle(SERVICE)}>
            <div style={{ fontWeight: 600 }}>MongoDB</div>
            <div style={{ fontSize: 10, color: "#888" }}>dedup by URL</div>
            {serviceTag()}
          </div>
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
          <div style={boxStyle(SERVICE)}>
            <div style={{ fontWeight: 600 }}>same collection</div>
            <div style={{ fontSize: 10, color: "#888" }}>backfilled: true</div>
            {serviceTag()}
          </div>
        </div>
      </div>

      {/* Backtest Pipeline */}
      <div style={section}>
        {sectionTitle("Backtest Pipeline", "#22c55e")}
        {processTag("runs inside FastAPI")}
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
          <div style={boxStyle(SOURCE)}>
            <div style={{ fontWeight: 600 }}>yfinance</div>
            <div style={{ fontSize: 10, color: "#888" }}>hourly / daily</div>
          </div>
          <span style={arrow}>→</span>
          <div style={boxStyle(SOURCE)}>
            <div style={{ fontWeight: 600 }}>News Events</div>
            <div style={{ fontSize: 10, color: "#888" }}>synthetic / real</div>
          </div>
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

      {/* State & Storage */}
      <div style={section}>
        {sectionTitle("State & Storage", "#c084fc")}
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <div style={boxStyle(STATE)}>
            <div style={{ fontWeight: 600 }}>Trader holdings</div>
            <div style={{ fontSize: 10, color: "#888" }}>in-memory dict</div>
            {stateTag()}
            <div style={{ fontSize: 9, color: "#666", marginTop: 2 }}>ephemeral — lost on restart</div>
          </div>
          <div style={boxStyle(STATE)}>
            <div style={{ fontWeight: 600 }}>PositionStore</div>
            <div style={{ fontSize: 10, color: "#888" }}>Redis key</div>
            {stateTag()}
            {pathTag("src/common/position_store.py")}
            <div style={{ fontSize: 9, color: "#666", marginTop: 2 }}>persistent — distributed mode</div>
          </div>
          <div style={boxStyle(STATE)}>
            <div style={{ fontWeight: 600 }}>Source _seen sets</div>
            <div style={{ fontSize: 10, color: "#888" }}>in-memory per source</div>
            {stateTag()}
            <div style={{ fontSize: 9, color: "#666", marginTop: 2 }}>ephemeral — dedup resets on restart</div>
          </div>
          <div style={boxStyle(SERVICE)}>
            <div style={{ fontWeight: 600 }}>MongoDB</div>
            <div style={{ fontSize: 10, color: "#888" }}>news + OHLCV</div>
            {serviceTag()}
            <div style={{ fontSize: 9, color: "#666", marginTop: 2 }}>persistent — backtest data</div>
          </div>
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
            <code style={{ fontSize: 10, color: "#818cf8" }}>python3 -m src.live.news_trader</code>
          </div>
          <div>
            <div style={{ fontWeight: 600, marginBottom: 4 }}>🔵 Distributed (separate processes)</div>
            <div style={{ color: "#888" }}>Each component runs independently.</div>
            <div style={{ color: "#888" }}>Uses RedisEventBus (cross-process).</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 2, marginTop: 4 }}>
              <code style={{ fontSize: 10, color: "#818cf8" }}>python3 -m src.live.runners.run_watcher</code>
              <code style={{ fontSize: 10, color: "#818cf8" }}>python3 -m src.live.runners.run_analyzer</code>
              <code style={{ fontSize: 10, color: "#818cf8" }}>python3 -m src.live.runners.run_trader</code>
              <code style={{ fontSize: 10, color: "#818cf8" }}>python3 -m src.live.runners.run_executor</code>
            </div>
          </div>
        </div>
      </div>

      {/* Requirements */}
      <div style={{ background: "#1a1a2e", borderRadius: 8, padding: 12, border: "1px solid #333" }}>
        {sectionTitle("Requirements", "#f59e0b")}
        <div style={{ display: "flex", gap: 24, fontSize: 11, color: "#888", flexWrap: "wrap" }}>
          <div>
            <div style={{ color: "#ccc", fontWeight: 600, marginBottom: 4 }}>API Keys (env vars)</div>
            {["NEWSAPI_KEY", "FINNHUB_KEY", "OPENAI_API_KEY (for LLM analyzer)", "TWITTER_BEARER_TOKEN (not wired yet)"].map((k) => (
              <div key={k} style={{ fontFamily: "monospace", fontSize: 10 }}>{k}</div>
            ))}
          </div>
          <div>
            <div style={{ color: "#ccc", fontWeight: 600, marginBottom: 4 }}>Services</div>
            <div style={{ fontSize: 10 }}>MongoDB — news storage & backtest data</div>
            <div style={{ fontSize: 10 }}>Redis — distributed mode + PositionStore</div>
            <div style={{ fontSize: 10 }}>Futu OpenD — live trading (optional, defaults to LogBroker)</div>
          </div>
        </div>
      </div>

      {/* Legend */}
      <div style={{ display: "flex", gap: 12, marginTop: 16, fontSize: 11, color: "#888", flexWrap: "wrap", alignItems: "center" }}>
        {processTag()} <span>standalone process</span>
        {internalTag()} <span>runs inside parent process</span>
        {serviceTag()} <span>external service</span>
        {stateTag()} <span>data / state</span>
        {disabledTag()} <span>defined but not yet connected</span>
      </div>
    </div>
  );
}
