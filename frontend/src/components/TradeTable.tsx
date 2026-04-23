import { Trade } from "../types/backtest";

interface Props {
  trades: Trade[];
}

export default function TradeTable({ trades }: Props) {
  return (
    <div style={{ background: "#1e1e2e", borderRadius: 8, padding: 16, overflowX: "auto" }}>
      <div style={{ fontSize: 14, color: "#888", marginBottom: 8 }}>Trade Log</div>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead>
          <tr style={{ borderBottom: "1px solid #333" }}>
            {["Date", "Symbol", "Action", "Shares", "Price", "Sentiment", "P&L", "Headline"].map((h) => (
              <th key={h} style={{ textAlign: "left", padding: "6px 8px", color: "#888", fontWeight: 500 }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {trades.map((t, i) => (
            <tr key={i} style={{ borderBottom: "1px solid #222" }}>
              <td style={{ padding: "6px 8px", color: "#ccc" }}>{t.date}</td>
              <td style={{ padding: "6px 8px", color: "#e0e0e0", fontWeight: 600 }}>{t.symbol}</td>
              <td style={{
                padding: "6px 8px",
                color: t.action.startsWith("buy") ? "#22c55e" : "#ef4444",
              }}>
                {t.action}
              </td>
              <td style={{ padding: "6px 8px", color: "#ccc" }}>{t.shares}</td>
              <td style={{ padding: "6px 8px", color: "#ccc" }}>${t.price.toFixed(2)}</td>
              <td style={{
                padding: "6px 8px",
                color: t.sentiment > 0 ? "#22c55e" : t.sentiment < 0 ? "#ef4444" : "#888",
              }}>
                {t.sentiment !== 0 ? (t.sentiment > 0 ? "+" : "") + t.sentiment.toFixed(2) : "—"}
              </td>
              <td style={{
                padding: "6px 8px",
                fontWeight: 600,
                color: t.pnl > 0 ? "#22c55e" : t.pnl < 0 ? "#ef4444" : "#888",
              }}>
                {t.pnl !== 0 ? `$${t.pnl > 0 ? "+" : ""}${t.pnl.toFixed(2)}` : "—"}
              </td>
              <td style={{ padding: "6px 8px", color: "#888", maxWidth: 250, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {t.headline}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
