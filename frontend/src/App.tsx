import { useState, useEffect, useRef } from "react";
import type { BacktestResult, BacktestParams } from "./types/backtest";
import { fetchBacktest, getNewsCount } from "./hooks/api";
import StatsCard from "./components/StatsCard";
import EquityChart from "./components/EquityChart";
import TradeTable from "./components/TradeTable";
import ParamsPanel from "./components/ParamsPanel";
import PnlBySymbol from "./components/PnlBySymbol";
import ArchitectureDiagram from "./components/ArchitectureDiagram";
import NewsFeed from "./components/NewsFeed";

const DEFAULT_PARAMS: BacktestParams = {
  capital: 70000,
  threshold: 0.4,
  max_allocation: 0.2,
  stop_loss: 0.05,
  take_profit: 0.10,
  max_hold_days: 30,
  trailing_sl: false,
};

type Tab = "backtest" | "news" | "about";

export default function App() {
  const [tab, setTab] = useState<Tab>("backtest");
  const [params, setParams] = useState<BacktestParams>(DEFAULT_PARAMS);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [newsCount, setNewsCount] = useState(0);
  const prevCount = useRef(0);
  const [newsBadge, setNewsBadge] = useState(0);

  useEffect(() => {
    const poll = setInterval(async () => {
      try {
        const count = await getNewsCount();
        if (prevCount.current > 0 && count > prevCount.current) {
          setNewsBadge((b) => b + (count - prevCount.current));
        }
        prevCount.current = count;
        setNewsCount(count);
      } catch {}
    }, 30000);
    getNewsCount().then((c) => { setNewsCount(c); prevCount.current = c; }).catch(() => {});
    return () => clearInterval(poll);
  }, []);

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
          <button style={tabStyle("news")} onClick={() => { setTab("news"); setNewsBadge(0); }}>
            News
            {newsBadge > 0 && (
              <span style={{
                marginLeft: 6, background: "#ef4444", color: "#fff",
                borderRadius: 10, padding: "1px 6px", fontSize: 10, fontWeight: 700,
              }}>{newsBadge}</span>
            )}
          </button>
          <button style={tabStyle("about")} onClick={() => setTab("about")}>About</button>
        </div>
      </div>

      <div style={{ maxWidth: 1100 }}>
        {tab === "news" && <NewsFeed />}

        {tab === "about" && <ArchitectureDiagram />}

        {tab === "backtest" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <ParamsPanel params={params} onChange={setParams} onRun={runBacktest} loading={loading} />
            {error && <div style={{ color: "#ef4444", background: "#2a1515", padding: 12, borderRadius: 8 }}>{error}</div>}
            {result && (
              <>
                <StatsCard result={result} />
                <PnlBySymbol trades={result.trades} />
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
