import { useState } from "react";
import { fetchLiveBacktest } from "../hooks/api";
import { DEFAULT_LIVE_PARAMS, LIVE_EXTRA_SLIDERS, formatSliderValue } from "../constants";
import StatsCard from "./StatsCard";
import EquityChart from "./EquityChart";
import TradeTable from "./TradeTable";
import PnlBySymbol from "./PnlBySymbol";

const sliders = LIVE_EXTRA_SLIDERS;

export default function LivePipelineBacktest() {
  const [params, setParams] = useState(DEFAULT_LIVE_PARAMS);
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
      const apiParams: Record<string, string | number> = {};
      for (const [k, v] of Object.entries(params)) {
        if (typeof v !== "boolean") apiParams[k] = v;
      }
      const data = await fetchLiveBacktest(apiParams, (pct, lines) => {
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

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ background: "#1e1e2e", borderRadius: 8, padding: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
          <span style={{ fontSize: 14, color: "#888" }}>Live Pipeline Backtest</span>
          <span style={{ fontSize: 9, background: "#22c55e22", color: "#22c55e", padding: "2px 6px", borderRadius: 3 }}>
            same code as production
          </span>
          <span style={{ fontSize: 9, background: "#818cf822", color: "#818cf8", padding: "2px 6px", borderRadius: 3 }}>
            single-process only
          </span>
        </div>
        <details style={{ fontSize: 11, color: "#666", marginBottom: 12 }}>
          <summary style={{ cursor: "pointer", color: "#888" }}>Why single-process only?</summary>
          <div style={{ marginTop: 6, lineHeight: 1.6, color: "#777" }}>
            <p style={{ margin: "4px 0" }}>The live pipeline backtest uses the same components as production but runs in single-process mode (LocalEventBus) because backtesting is inherently a simulation — it needs a controlled clock and sequential execution.</p>
            <ol style={{ margin: "6px 0", paddingLeft: 20 }}>
              <li><strong style={{ color: "#ccc" }}>Historical timestamps</strong> — PriceMonitor needs to step through past timestamps. In distributed mode it polls live prices on a 60s timer.</li>
              <li><strong style={{ color: "#ccc" }}>Sequential execution</strong> — The backtest must process events in order: publish news → wait for fill → check SL/TP → next news. Distributed components run independently with no synchronization.</li>
              <li><strong style={{ color: "#ccc" }}>Price lookups</strong> — Each SL/TP check calls yfinance. Hourly checks across months = thousands of API calls. Single-process can use ClickHouse cache; distributed containers would each hit yfinance independently.</li>
            </ol>
            <p style={{ margin: "4px 0" }}>Distributed mode is for live trading where events arrive naturally. Backtesting = single process, live trading = distributed. Same component code, different wiring.</p>
          </div>
        </details>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
          {sliders.map((f) => (
            <div key={f.key}>
              <label style={{ fontSize: 11, color: "#888" }}>
                {f.label}: <strong style={{ color: "#e0e0e0" }}>{formatSliderValue(f.key, (params as any)[f.key])}</strong>
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
