import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts";

interface Props {
  data: number[];
  initialCapital: number;
}

export default function EquityChart({ data, initialCapital }: Props) {
  const chartData = data.map((v, i) => ({ bar: i, value: Math.round(v * 100) / 100 }));

  return (
    <div style={{ background: "#1e1e2e", borderRadius: 8, padding: 16 }}>
      <div style={{ fontSize: 14, color: "#888", marginBottom: 8 }}>Equity Curve</div>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={chartData}>
          <XAxis dataKey="bar" tick={false} />
          <YAxis domain={["auto", "auto"]} tick={{ fill: "#888", fontSize: 12 }} />
          <Tooltip
            contentStyle={{ background: "#2a2a3e", border: "none", borderRadius: 6 }}
            labelStyle={{ color: "#888" }}
            formatter={(v: number) => [`$${v.toLocaleString()}`, "Value"]}
          />
          <ReferenceLine y={initialCapital} stroke="#555" strokeDasharray="3 3" />
          <Line type="monotone" dataKey="value" stroke="#818cf8" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
