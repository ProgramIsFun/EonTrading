import { useState } from "react";
import { fetchPriceBacktest } from "../hooks/api";
import StatsCard from "./StatsCard";
import EquityChart from "./EquityChart";
import TradeTable from "./TradeTable";

interface PriceResult {
  strategy: string;
  symbol: string;
  initial_capital: number;
  final_value: number;
  total_return_pct: number;
  annual_return_pct: number;
  max_drawdown_pct: number;
  total_trades: number;
  win_rate: number;
  sharpe_ratio: number;
  equity_curve: number[];
  trades: { symbol: string; side: string; entry_price: number; exit_price: number; shares: number; pnl: number; entry_date: string; exit_date: string }[];
}

export default function PriceBacktest() {
  const [symbol, setSymbol] = useState("AAPL");
  const [strategy, setStrategy] = useState("sma");
  const [capital, setCapital] = useState(10000);
  const [fast, setFast] = useState(20);
  const [slow, setSlow] = useState(50);
  const [period, setPeriod] = useState(14);
  const [oversold, setOversold] = useState(30);
  const [overbought, setOverbought] = useState(70);
  const [result, setResult] = useState<PriceResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const run = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await fetchPriceBacktest({
        symbol, strategy, capital: String(capital),
        fast: String(fast), slow: String(slow),
        period: String(period), oversold: String(oversold), overbought: String(overbought),
      });
      if (data.error) throw new Error(data.error);
      setResult(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const inputStyle = { background: "#2a2a3e", border: "1px solid #333", borderRadius: 4, padding: "4px 8px", color: "#e0e0e0", fontSize: 13, width: 80 };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ background: "#1e1e2e", borderRadius: 8, padding: 16 }}>
        <div style={{ fontSize: 14, color: "#888", marginBottom: 12 }}>Price-Based Backtest</div>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
          <label style={{ fontSize: 12, color: "#888" }}>Symbol:
            <input value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} style={{ ...inputStyle, marginLeft: 4 }} />
          </label>
          <label style={{ fontSize: 12, color: "#888" }}>Strategy:
            <select value={strategy} onChange={(e) => setStrategy(e.target.value)} style={{ ...inputStyle, marginLeft: 4, width: 100 }}>
              <option value="sma">SMA Crossover</option>
              <option value="rsi">RSI Mean Reversion</option>
            </select>
          </label>
          <label style={{ fontSize: 12, color: "#888" }}>Capital:
            <input type="number" value={capital} onChange={(e) => setCapital(Number(e.target.value))} style={{ ...inputStyle, marginLeft: 4 }} />
          </label>
          {strategy === "sma" && (
            <>
              <label style={{ fontSize: 12, color: "#888" }}>Fast: <input type="number" value={fast} onChange={(e) => setFast(Number(e.target.value))} style={{ ...inputStyle, marginLeft: 4, width: 50 }} /></label>
              <label style={{ fontSize: 12, color: "#888" }}>Slow: <input type="number" value={slow} onChange={(e) => setSlow(Number(e.target.value))} style={{ ...inputStyle, marginLeft: 4, width: 50 }} /></label>
            </>
          )}
          {strategy === "rsi" && (
            <>
              <label style={{ fontSize: 12, color: "#888" }}>Period: <input type="number" value={period} onChange={(e) => setPeriod(Number(e.target.value))} style={{ ...inputStyle, marginLeft: 4, width: 50 }} /></label>
              <label style={{ fontSize: 12, color: "#888" }}>Oversold: <input type="number" value={oversold} onChange={(e) => setOversold(Number(e.target.value))} style={{ ...inputStyle, marginLeft: 4, width: 50 }} /></label>
              <label style={{ fontSize: 12, color: "#888" }}>Overbought: <input type="number" value={overbought} onChange={(e) => setOverbought(Number(e.target.value))} style={{ ...inputStyle, marginLeft: 4, width: 50 }} /></label>
            </>
          )}
          <button onClick={run} disabled={loading} style={{
            padding: "6px 20px", background: loading ? "#555" : "#818cf8",
            color: "#fff", border: "none", borderRadius: 6, cursor: loading ? "wait" : "pointer", fontSize: 13, fontWeight: 600,
          }}>{loading ? "Running..." : "Run"}</button>
        </div>
        {error && <div style={{ color: "#ef4444", marginTop: 8 }}>{error}</div>}
      </div>

      {result && (
        <>
          <StatsCard result={{
            initial_capital: result.initial_capital,
            final_value: result.final_value,
            total_return_pct: result.total_return_pct,
            max_drawdown_pct: result.max_drawdown_pct,
            total_trades: result.total_trades,
            win_rate: result.win_rate,
            equity_curve: result.equity_curve,
            trades: result.trades.map(t => ({
              ...t, action: t.side, date: t.entry_date, price: t.entry_price,
              sentiment: 0, headline: "",
            })),
          }} />

          <EquityChart data={result.equity_curve} initialCapital={capital} />

          <TradeTable trades={result.trades.map(t => ({
            ...t, action: t.side, date: t.entry_date, price: t.entry_price,
            sentiment: 0, headline: "",
          }))} />
        </>
      )}
    </div>
  );
}
