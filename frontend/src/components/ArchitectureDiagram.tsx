const boxStyle = (color: string) => ({
  background: color,
  borderRadius: 8,
  padding: "8px 14px",
  fontSize: 12,
  color: "#e0e0e0",
  textAlign: "center" as const,
  minWidth: 100,
});

const processTag = (text: string) => (
  <span style={{ fontSize: 9, background: "#818cf822", color: "#818cf8", padding: "1px 5px", borderRadius: 3, marginLeft: 4 }}>{text}</span>
);
const internalTag = () => (
  <span style={{ fontSize: 9, background: "#22c55e22", color: "#22c55e", padding: "1px 5px", borderRadius: 3 }}>internal</span>
);
const serviceTag = () => (
  <span style={{ fontSize: 9, background: "#f59e0b22", color: "#f59e0b", padding: "1px 5px", borderRadius: 3 }}>service</span>
);

const arrow = { color: "#555", fontSize: 18 };
const label = (text: string) => <span style={{ fontSize: 10, color: "#666" }}>{text}</span>;

export default function ArchitectureDiagram() {
  return (
    <div style={{ background: "#1e1e2e", borderRadius: 8, padding: 24 }}>
      <div style={{ fontSize: 14, color: "#888", marginBottom: 16 }}>System Architecture</div>

      {/* Legend */}
      <div style={{ display: "flex", gap: 12, marginBottom: 16, fontSize: 11, color: "#888", flexWrap: "wrap" }}>
        {processTag("process")} <span>= standalone process</span>
        <span style={{ fontSize: 9, background: "#22c55e22", color: "#22c55e", padding: "1px 5px", borderRadius: 3 }}>internal</span> <span>= runs inside another process</span>
        <span style={{ fontSize: 9, background: "#f59e0b22", color: "#f59e0b", padding: "1px 5px", borderRadius: 3 }}>service</span> <span>= external service</span>
      </div>

      {/* Live Pipeline */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 12, color: "#818cf8", marginBottom: 8, fontWeight: 600 }}>Live Trading Pipeline {processTag("python3 -m src.live.news_trader")}</div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <div style={{ display: "flex", gap: 6 }}>
            {["NewsAPI", "Finnhub", "RSS", "Reddit"].map((s) => (
              <div key={s} style={boxStyle("#2a2a4a")}>{s}</div>
            ))}
          </div>
          <span style={arrow}>→</span>
          <div style={boxStyle("#1e3a2e")}>
            <div style={{ fontWeight: 600 }}>NewsWatcher</div>
            <div style={{ fontSize: 10, color: "#888" }}>poll + dedup</div>
            {internalTag()}
          </div>
          <span style={arrow}>→</span>
          <div style={boxStyle("#2a2a4a")}>
            <div style={{ fontWeight: 600 }}>Sentiment Analyzer</div>
            <div style={{ fontSize: 10, color: "#888" }}>Keyword / LLM (direct call)</div>
            {internalTag()}
          </div>
          <span style={arrow}>→</span>
          {label("[sentiment]")}
          <span style={arrow}>→</span>
          <div style={boxStyle("#3a2a1e")}>
            <div style={{ fontWeight: 600 }}>SentimentTrader</div>
            <div style={{ fontSize: 10, color: "#818cf8" }}>TradingLogic ↗</div>
            {internalTag()}
          </div>
          <span style={arrow}>→</span>
          {label("[trade]")}
          <span style={arrow}>→</span>
          <div style={boxStyle("#2a2a4a")}>
            <div style={{ fontWeight: 600 }}>Executor</div>
            <div style={{ fontSize: 10, color: "#888" }}>Log / Futu</div>
            {internalTag()}
          </div>
        </div>
      </div>

      {/* News Data Pipeline */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 12, color: "#f472b6", marginBottom: 8, fontWeight: 600 }}>News Data Pipeline → MongoDB (EonTradingDB.news)</div>

        {/* Live collector */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
          <span style={{ fontSize: 10, color: "#888", width: 70 }}>Live: {processTag("process")}</span>
          <div style={{ display: "flex", gap: 6 }}>
            {["RSS (free)", "Reddit (free)"].map((s) => (
              <div key={s} style={boxStyle("#2a2a4a")}>{s}</div>
            ))}
          </div>
          <span style={arrow}>→</span>
          <div style={boxStyle("#1e3a2e")}>
            <div style={{ fontWeight: 600 }}>collect_news.py</div>
            <div style={{ fontSize: 10, color: "#888" }}>poll every 5min</div>
          </div>
          <span style={arrow}>→</span>
          <div style={boxStyle("#3a2a1e")}>
            <div style={{ fontWeight: 600 }}>MongoDB</div>
            <div style={{ fontSize: 10, color: "#888" }}>dedup by URL</div>
            {serviceTag()}
          </div>
        </div>

        {/* Backfill */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span style={{ fontSize: 10, color: "#888", width: 70 }}>Backfill: {processTag("one-off")}</span>
          <div style={{ display: "flex", gap: 6 }}>
            {["Finnhub (key)", "NewsAPI (key)"].map((s) => (
              <div key={s} style={boxStyle("#2a2a4a")}>{s}</div>
            ))}
          </div>
          <span style={arrow}>→</span>
          <div style={boxStyle("#1e3a2e")}>
            <div style={{ fontWeight: 600 }}>backfill_news.py</div>
            <div style={{ fontSize: 10, color: "#888" }}>historical, per symbol</div>
          </div>
          <span style={arrow}>→</span>
          <div style={boxStyle("#3a2a1e")}>
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
          <div style={boxStyle("#2a2a4a")}>
            <div style={{ fontWeight: 600 }}>News Events</div>
            <div style={{ fontSize: 10, color: "#888" }}>synthetic / real</div>
          </div>
          <span style={arrow}>→</span>
          <div style={boxStyle("#2a2a4a")}>
            <div style={{ fontWeight: 600 }}>Analyzer</div>
          </div>
          <span style={arrow}>→</span>
          <div style={boxStyle("#3a2a1e")}>
            <div style={{ fontWeight: 600 }}>Backtest Engine</div>
            <div style={{ fontSize: 10, color: "#818cf8" }}>TradingLogic ↗</div>
          </div>
          <span style={arrow}>←</span>
          <div style={boxStyle("#2a2a4a")}>
            <div style={{ fontWeight: 600 }}>yfinance</div>
            <div style={{ fontSize: 10, color: "#888" }}>hourly / daily</div>
          </div>
        </div>
      </div>

      {/* Dashboard */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 12, color: "#f59e0b", marginBottom: 8, fontWeight: 600 }}>Dashboard</div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <div style={boxStyle("#2a2a4a")}>
            <div style={{ fontWeight: 600 }}>React + Vite</div>
            <div style={{ fontSize: 10, color: "#888" }}>charts, controls</div>
            <div>{processTag("npm run dev")}</div>
          </div>
          <span style={arrow}>→ HTTP →</span>
          <div style={boxStyle("#2a2a4a")}>
            <div style={{ fontWeight: 600 }}>FastAPI</div>
            <div style={{ fontSize: 10, color: "#888" }}>/api/backtest</div>
            <div>{processTag("uvicorn")}</div>
          </div>
          <span style={arrow}>→</span>
          <div style={boxStyle("#3a2a1e")}>
            <div style={{ fontWeight: 600 }}>Backtest Engine</div>
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
