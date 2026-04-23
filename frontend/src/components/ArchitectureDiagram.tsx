// Colors: process=blue, internal=green, service=amber, source=neutral
const PROCESS = "#1a2a4a";
const INTERNAL = "#1a3a2a";
const SERVICE = "#3a2a1a";
const SOURCE = "#2a2a3a";

const borders: Record<string, string> = {
  [PROCESS]: "#818cf844",
  [INTERNAL]: "#22c55e44",
  [SERVICE]: "#f59e0b44",
  [SOURCE]: "#44444466",
};

const boxStyle = (color: string) => ({
  background: color,
  borderRadius: 8,
  padding: "8px 14px",
  fontSize: 12,
  color: "#e0e0e0",
  textAlign: "center" as const,
  minWidth: 100,
  border: `1px solid ${borders[color] || "#333"}`,
});

const tag = (text: string, bg: string, fg: string) => (
  <span style={{ fontSize: 9, background: bg, color: fg, padding: "1px 5px", borderRadius: 3 }}>{text}</span>
);
const processTag = (t?: string) => tag(t || "process", "#818cf822", "#818cf8");
const internalTag = () => tag("internal", "#22c55e22", "#22c55e");
const serviceTag = () => tag("service", "#f59e0b22", "#f59e0b");
const pathTag = (p: string) => (
  <div style={{ fontSize: 9, color: "#555", fontFamily: "monospace", marginTop: 2 }}>{p}</div>
);

const arrow = { color: "#555", fontSize: 18 };
const label = (text: string) => <span style={{ fontSize: 10, color: "#666" }}>{text}</span>;

export default function ArchitectureDiagram() {
  return (
    <div style={{ background: "#1e1e2e", borderRadius: 8, padding: 24 }}>
      <div style={{ fontSize: 14, color: "#888", marginBottom: 16 }}>System Architecture</div>

      {/* Legend */}
      <div style={{ display: "flex", gap: 12, marginBottom: 20, fontSize: 11, color: "#888", flexWrap: "wrap", alignItems: "center" }}>
        {processTag()} <span>standalone process</span>
        {internalTag()} <span>runs inside parent process</span>
        {serviceTag()} <span>external service</span>
      </div>

      {/* Mode explanation */}
      <div style={{ background: "#1a1a2e", borderRadius: 8, padding: 12, marginBottom: 20, border: "1px solid #333" }}>
        <div style={{ fontSize: 12, color: "#818cf8", fontWeight: 600, marginBottom: 6 }}>Deployment Modes</div>
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
              <code style={{ fontSize: 10, color: "#818cf8" }}>python3 -m src.live.runners.run_trader</code>
              <code style={{ fontSize: 10, color: "#818cf8" }}>python3 -m src.live.runners.run_executor</code>
            </div>
          </div>
        </div>
        <div style={{ marginTop: 10, fontSize: 10, color: "#888", lineHeight: 1.6, borderTop: "1px solid #333", paddingTop: 8 }}>
          <div style={{ fontWeight: 600, color: "#ccc", marginBottom: 4 }}>Channel routing (both modes):</div>
          <div>Watcher → publishes to <code style={{ color: "#818cf8" }}>sentiment</code> channel</div>
          <div>Trader → subscribes to <code style={{ color: "#818cf8" }}>sentiment</code>, publishes to <code style={{ color: "#818cf8" }}>trade</code> channel</div>
          <div>Executor → subscribes to <code style={{ color: "#818cf8" }}>trade</code> channel</div>
          <div style={{ color: "#555", marginTop: 4 }}>Same channels whether LocalEventBus (in-memory) or RedisEventBus (cross-process).</div>
        </div>
        </div>
        <div style={{ fontSize: 10, color: "#666", marginTop: 8 }}>Same components, same logic — only the event bus changes. Switch anytime with no code changes.</div>
      </div>

      {/* Live Pipeline */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 12, color: "#818cf8", marginBottom: 8, fontWeight: 600 }}>
          Live Trading Pipeline
        </div>
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
          </div>
          <span style={arrow}>→</span>
          <div style={boxStyle(INTERNAL)}>
            <div style={{ fontWeight: 600 }}>NewsWatcher</div>
            {internalTag()}
            {pathTag("src/live/news_watcher.py")}
            {pathTag("src/common/news_poller.py")}
          </div>
          <span style={arrow}>→</span>
          <div style={boxStyle(INTERNAL)}>
            <div style={{ fontWeight: 600 }}>Sentiment Analyzer</div>
            <div style={{ fontSize: 10, color: "#888" }}>Keyword / LLM</div>
            {internalTag()}
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
      </div>

      {/* News Data Pipeline */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 12, color: "#f472b6", marginBottom: 8, fontWeight: 600 }}>News Data Pipeline → MongoDB (EonTradingDB.news)</div>

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
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 12, color: "#22c55e", marginBottom: 8, fontWeight: 600 }}>Backtest Pipeline {processTag("runs inside FastAPI")}</div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
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
          <span style={arrow}>←</span>
          <div style={boxStyle(SOURCE)}>
            <div style={{ fontWeight: 600 }}>yfinance</div>
            <div style={{ fontSize: 10, color: "#888" }}>hourly / daily</div>
          </div>
        </div>
      </div>

      {/* Dashboard */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 12, color: "#f59e0b", marginBottom: 8, fontWeight: 600 }}>Dashboard</div>
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
      </div>

      {/* Shared */}
      <div style={{ borderTop: "1px solid #333", paddingTop: 12 }}>
        <div style={{ fontSize: 12, color: "#818cf8", marginBottom: 8, fontWeight: 600 }}>Shared: TradingLogic</div>
        {pathTag("src/common/trading_logic.py")}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", fontSize: 11, color: "#888", marginTop: 6 }}>
          {["should_buy()", "should_sell_on_sentiment()", "check_stop_loss()", "check_take_profit()", "update_peak()"].map((m) => (
            <span key={m} style={{ background: "#2a2a3e", padding: "4px 8px", borderRadius: 4, fontFamily: "monospace" }}>{m}</span>
          ))}
        </div>
        <div style={{ fontSize: 11, color: "#666", marginTop: 8 }}>
          Cash only — no margin, no leverage, no short selling. Max loss = initial capital.
        </div>
      </div>
    </div>
  );
}
