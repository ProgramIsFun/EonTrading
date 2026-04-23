import { useState } from "react";
import type { BacktestResult, BacktestParams } from "./types/backtest";
import { fetchBacktest } from "./hooks/api";
import StatsCard from "./components/StatsCard";
import EquityChart from "./components/EquityChart";
import TradeTable from "./components/TradeTable";
import ParamsPanel from "./components/ParamsPanel";
import ArchitectureDiagram from "./components/ArchitectureDiagram";

const DEFAULT_PARAMS: BacktestParams = {
  capital: 70000,
  threshold: 0.4,
  max_allocation: 0.2,
  stop_loss: 0.05,
  take_profit: 0.10,
  max_hold_days: 30,
  trailing_sl: false,
};

type Tab = "backtest" | "about";

export default function App() {
  const [tab, setTab] = useState<Tab>("backtest");
  const [params, setParams] = useState<BacktestParams>(DEFAULT_PARAMS);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const runBacktest = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await fetchBacktest(params);
      setResult(data);
    } catch (e: any) {
      setError(e.message || "Failed to run backtest");
    } finally {
      setLoading(false);
    }
  };

  const tabStyle = (t: Tab) => ({
    padding: "8px 20px",
    background: tab === t ? "#818cf8" : "transparent",
    color: tab === t ? "#fff" : "#888",
    border: "none",
    borderRadius: 6,
    cursor: "pointer" as const,
    fontSize: 13,
    fontWeight: 600 as const,
  });

  return (
    <div style={{ background: "#121220", color: "#e0e0e0", minHeight: "100vh", padding: 24, fontFamily: "system-ui, sans-serif" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0 }}>EonTrading</h1>
        <div style={{ display: "flex", gap: 4, background: "#1e1e2e", borderRadius: 8, padding: 4 }}>
          <button style={tabStyle("backtest")} onClick={() => setTab("backtest")}>Backtest</button>
          <button style={tabStyle("about")} onClick={() => setTab("about")}>About</button>
        </div>
      </div>

      <div style={{ maxWidth: 1100 }}>
        {tab === "about" && <ArchitectureDiagram />}

        {tab === "backtest" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <ParamsPanel params={params} onChange={setParams} onRun={runBacktest} loading={loading} />
            {error && <div style={{ color: "#ef4444", background: "#2a1515", padding: 12, borderRadius: 8 }}>{error}</div>}
            {result && (
              <>
                <StatsCard result={result} />
                <EquityChart data={result.equity_curve} initialCapital={params.capital} />
                <TradeTable trades={result.trades} />
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
