import { useState } from "react";
import { fetchLiveBacktest } from "../hooks/api";
import StatsCard from "./StatsCard";
import EquityChart from "./EquityChart";
import TradeTable from "./TradeTable";
import PnlBySymbol from "./PnlBySymbol";

const defaults = {
  capital: 70000,
  threshold: 0.4,
  max_allocation: 0.2,
  stop_loss: 0.05,
  take_profit: 0.10,
  max_hold_days: 30,
  sl_check_hours: 24,
  analyzer: "keyword",
  cost_model: "us_stocks",
  news_source: "sample",
};

const sliders = [
  { key: "capital", label: "Capital ($)", min: 1000, max: 1000000, step: 1000 },
  { key: "threshold", label: "Sentiment Threshold", min: 0.1, max: 1.0, step: 0.05 },
  { key: "max_allocation", label: "Max Allocation (%)", min: 0.05, max: 1.0, step: 0.05 },
  { key: "stop_loss", label: "Stop Loss (%)", min: 0.01, max: 0.20, step: 0.01 },
  { key: "take_profit", label: "Take Profit (%)", min: 0.01, max: 0.50, step: 0.01 },
  { key: "max_hold_days", label: "Max Hold (days)", min: 1, max: 90, step: 1 },
  { key: "sl_check_hours", label: "SL/TP Check Interval (hours)", min: 1, max: 168, step: 1 },
] as const;

export default function LivePipelineBacktest() {
  const [params, setParams] = useState(defaults);
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [log, setLog] = useState<string[]>([]);
  const [error, setError] = useState("");

  const run = async () => {
    setLoading(true);
    setProgress(0);
    setLog([]);
    setError("");
    try {
      const data = await fetchLiveBacktest(params, (pct, lines) => {
        setProgress(pct);
        setLog(lines);
      });
      setResult(data);
    } catch (e: any) {
      setError(e.message || "Failed");
    } finally {
      setLoading(false);
    }
  };

  const fmt = (key: string, val: number) =>
    key === "capital" ? `$${val.toLocaleString()}` :
    key === "max_hold_days" || key === "sl_check_hours" ? val :
    `${(val * 100).toFixed(0)}%`;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ background: "#1e1e2e", borderRadius: 8, padding: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
          <span style={{ fontSize: 14, color: "#888" }}>Live Pipeline Backtest</span>
          <span style={{ fontSize: 9, background: "#22c55e22", color: "#22c55e", padding: "2px 6px", borderRadius: 3 }}>
            same code as production
          </span>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
          {sliders.map((f) => (
            <div key={f.key}>
              <label style={{ fontSize: 11, color: "#888" }}>
                {f.label}: <strong style={{ color: "#e0e0e0" }}>{fmt(f.key, (params as any)[f.key])}</strong>
              </label>
              <input
                type="range" min={f.min} max={f.max} step={f.step}
                value={(params as any)[f.key]}
                onChange={(e) => setParams({ ...params, [f.key]: Number(e.target.value) })}
                style={{ width: "100%", accentColor: "#818cf8" }}
              />
            </div>
          ))}
        </div>

        <div style={{ marginTop: 12, display: "flex", alignItems: "center", gap: 16 }}>
          <select
            value={params.analyzer}
            onChange={(e) => setParams({ ...params, analyzer: e.target.value })}
            style={{ background: "#2a2a3e", color: "#ccc", border: "1px solid #333", borderRadius: 4, padding: "6px 10px", fontSize: 13 }}
          >
            <option value="keyword">Keyword Analyzer (free)</option>
            <option value="llm">LLM Analyzer (needs API key)</option>
          </select>

          <select
            value={params.cost_model}
            onChange={(e) => setParams({ ...params, cost_model: e.target.value })}
            style={{ background: "#2a2a3e", color: "#ccc", border: "1px solid #333", borderRadius: 4, padding: "6px 10px", fontSize: 13 }}
          >
            <option value="us_stocks">US Stocks ($0.99 + 0.05% slippage)</option>
            <option value="hk_stocks">HK Stocks (0.1% stamp duty)</option>
            <option value="crypto">Crypto (0.1% commission)</option>
            <option value="zero">Zero costs (testing)</option>
          </select>

          <select
            value={params.news_source}
            onChange={(e) => setParams({ ...params, news_source: e.target.value })}
            style={{ background: "#2a2a3e", color: "#ccc", border: "1px solid #333", borderRadius: 4, padding: "6px 10px", fontSize: 13 }}
          >
            <option value="sample">Sample News (15 events)</option>
            <option value="mongodb">MongoDB (collected articles)</option>
          </select>

          <button onClick={run} disabled={loading} style={{
            padding: "8px 24px", background: loading ? "#555" : "#818cf8",
            color: "#fff", border: "none", borderRadius: 6,
            cursor: loading ? "wait" : "pointer", fontSize: 14, fontWeight: 600,
          }}>
            {loading ? `Running pipeline... ${progress}%` : "Run Live Backtest"}
          </button>
        </div>
      </div>

      {error && <div style={{ color: "#ef4444", background: "#2a1515", padding: 12, borderRadius: 8 }}>{error}</div>}

      {loading && log.length > 0 && (
        <div style={{ background: "#1e1e2e", borderRadius: 8, padding: 16, fontFamily: "monospace", fontSize: 12, maxHeight: 300, overflowY: "auto" }}>
          <div style={{ fontSize: 13, color: "#888", marginBottom: 8 }}>Pipeline Output ({progress}%)</div>
          {log.map((line, i) => (
            <div key={i} style={{ color: line.startsWith("✅") ? "#22c55e" : line.startsWith("❌") ? "#ef4444" : line.startsWith("⏰") ? "#f59e0b" : "#ccc", padding: "1px 0" }}>
              {line}
            </div>
          ))}
        </div>
      )}

      {result && (
        <>
          <StatsCard result={result} />

          {result.open_positions?.length > 0 && (
            <div style={{ background: "#1e1e2e", borderRadius: 8, padding: 16 }}>
              <div style={{ fontSize: 14, color: "#888", marginBottom: 8 }}>Open Positions at End</div>
              <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                {result.open_positions.map((p: any) => (
                  <div key={p.symbol} style={{ background: "#2a2a3e", borderRadius: 6, padding: "8px 14px" }}>
                    <div style={{ fontWeight: 600, color: "#e0e0e0" }}>{p.symbol}</div>
                    <div style={{ fontSize: 11, color: "#888" }}>{p.qty} shares @ ${p.price}</div>
                    <div style={{ fontSize: 11, color: "#22c55e" }}>${p.value.toLocaleString()}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <PnlBySymbol trades={result.trades} />
          <EquityChart data={result.equity_curve} initialCapital={params.capital} />
          <TradeTable trades={result.trades} />
        </>
      )}
    </div>
  );
}
