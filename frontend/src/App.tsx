import { useState } from "react";
import type { BacktestResult, BacktestParams } from "./types/backtest";
import { fetchBacktest } from "./hooks/api";
import StatsCard from "./components/StatsCard";
import EquityChart from "./components/EquityChart";
import TradeTable from "./components/TradeTable";
import ParamsPanel from "./components/ParamsPanel";

const DEFAULT_PARAMS: BacktestParams = {
  capital: 70000,
  threshold: 0.4,
  max_allocation: 0.2,
  stop_loss: 0.05,
  take_profit: 0.10,
  max_hold_days: 30,
};

export default function App() {
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

  return (
    <div style={{ background: "#121220", color: "#e0e0e0", minHeight: "100vh", padding: 24, fontFamily: "system-ui, sans-serif" }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 4 }}>EonTrading</h1>
      <p style={{ color: "#888", fontSize: 13, marginBottom: 24 }}>Sentiment-driven trading backtest dashboard</p>

      <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 1100 }}>
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
    </div>
  );
}
