import type { BacktestResult } from "../types/backtest";

interface Props {
  result: BacktestResult;
}

export default function StatsCard({ result }: Props) {
  const stats = [
    { label: "Return", value: `${result.total_return_pct >= 0 ? "+" : ""}${result.total_return_pct}%`, color: result.total_return_pct >= 0 ? "#22c55e" : "#ef4444" },
    { label: "Final Value", value: `$${result.final_value.toLocaleString()}` },
    { label: "Max Drawdown", value: `${result.max_drawdown_pct}%`, color: "#ef4444" },
    { label: "Trades", value: result.total_trades },
    { label: "Win Rate", value: `${result.win_rate}%`, color: result.win_rate >= 50 ? "#22c55e" : "#f59e0b" },
  ];

  return (
    <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
      {stats.map((s) => (
        <div key={s.label} style={{ background: "#1e1e2e", borderRadius: 8, padding: "12px 20px", minWidth: 120 }}>
          <div style={{ fontSize: 12, color: "#888" }}>{s.label}</div>
          <div style={{ fontSize: 22, fontWeight: 700, color: s.color || "#e0e0e0" }}>
            {s.value}
          </div>
        </div>
      ))}
    </div>
  );
}
