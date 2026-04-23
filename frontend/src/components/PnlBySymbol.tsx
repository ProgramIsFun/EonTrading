import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import type { Trade } from "../types/backtest";

interface Props {
  trades: Trade[];
}

export default function PnlBySymbol({ trades }: Props) {
  const pnlMap: Record<string, number> = {};
  for (const t of trades) {
    if (t.pnl !== 0) {
      pnlMap[t.symbol] = (pnlMap[t.symbol] || 0) + t.pnl;
    }
  }

  const data = Object.entries(pnlMap)
    .map(([symbol, pnl]) => ({ symbol, pnl: Math.round(pnl * 100) / 100 }))
    .sort((a, b) => b.pnl - a.pnl);

  if (data.length === 0) return null;

  return (
    <div style={{ background: "#1e1e2e", borderRadius: 8, padding: 16 }}>
      <div style={{ fontSize: 14, color: "#888", marginBottom: 8 }}>P&L by Symbol</div>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={data}>
          <XAxis dataKey="symbol" tick={{ fill: "#ccc", fontSize: 12 }} />
          <YAxis tick={{ fill: "#888", fontSize: 12 }} />
          <Tooltip
            contentStyle={{ background: "#2a2a3e", border: "none", borderRadius: 6 }}
            formatter={(v: number) => [`$${v.toLocaleString()}`, "P&L"]}
          />
          <Bar dataKey="pnl" radius={[4, 4, 0, 0]}>
            {data.map((d, i) => (
              <Cell key={i} fill={d.pnl >= 0 ? "#22c55e" : "#ef4444"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
