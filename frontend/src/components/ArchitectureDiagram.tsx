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

      {/* Live Pipeline */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 12, color: "#818cf8", marginBottom: 8, fontWeight: 600 }}>Live Trading Pipeline {processTag("python3 -m src.live.news_trader")}</div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <div style={{ display: "flex", gap: 6 }}>
            {["NewsAPI", "Finnhub", "RSS", "Reddit"].map((s) => (
              <div key={s} style={boxStyle(SOURCE)}>{s}</div>
            ))}
          </div>
          <span style={arrow}>→</span>
          <div style={boxStyle(INTERNAL)}>
            <div style={{ fontWeight: 600 }}>NewsWatcher</div>
            <div style={{ fontSize: 10, color: "#888" }}>poll + dedup</div>
            {internalTag()}
          </div>
          <span style={arrow}>→</span>
          <div style={boxStyle(INTERNAL)}>
            <div style={{ fontWeight: 600 }}>Sentiment Analyzer</div>
            <div style={{ fontSize: 10, color: "#888" }}>Keyword / LLM</div>
            {internalTag()}
          </div>
          <span style={arrow}>→</span>
          {label("[sentiment]")}
          <span style={arrow}>→</span>
          <div style={boxStyle(INTERNAL)}>
            <div style={{ fontWeight: 600 }}>SentimentTrader</div>
            <div style={{ fontSize: 10, color: "#818cf8" }}>TradingLogic ↗</div>
            {internalTag()}
          </div>
          <span style={arrow}>→</span>
          {label("[trade]")}
          <span style={arrow}>→</span>
          <div style={boxStyle(INTERNAL)}>
            <div style={{ fontWeight: 600 }}>Executor</div>
            <div style={{ fontSize: 10, color: "#888" }}>Log / Futu</div>
            {internalTag()}
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
          </div>
          <span style={arrow}>→</span>
          <div style={boxStyle(INTERNAL)}>
            <div style={{ fontWeight: 600 }}>Backtest Engine</div>
            <div style={{ fontSize: 10, color: "#818cf8" }}>TradingLogic ↗</div>
            {internalTag()}
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
          </div>
          <span style={arrow}>→ HTTP →</span>
          <div style={boxStyle(PROCESS)}>
            <div style={{ fontWeight: 600 }}>FastAPI</div>
            <div style={{ fontSize: 10, color: "#888" }}>/api/backtest</div>
            {processTag("uvicorn")}
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
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", fontSize: 11, color: "#888" }}>
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
