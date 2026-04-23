import { useEffect, useState } from "react";
import { fetchNews, getCollectorStatus, toggleCollector } from "../hooks/api";

interface NewsItem {
  source: string;
  headline: string;
  timestamp: string;
  url: string;
  collected_at: string;
}

export default function NewsFeed() {
  const [news, setNews] = useState<NewsItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [collecting, setCollecting] = useState(false);

  const loadNews = () => fetchNews().then(setNews).finally(() => setLoading(false));

  useEffect(() => {
    loadNews();
    getCollectorStatus().then(setCollecting).catch(() => {});
  }, []);

  const handleToggle = async () => {
    await toggleCollector(!collecting);
    setCollecting(!collecting);
  };

  const sourceColor = (s: string) => {
    if (s.startsWith("reddit")) return "#ff4500";
    if (s === "rss") return "#f59e0b";
    return "#818cf8";
  };

  return (
    <div style={{ background: "#1e1e2e", borderRadius: 8, padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div style={{ fontSize: 14, color: "#888" }}>
          News Feed ({news.length} articles)
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button onClick={loadNews} style={{
            padding: "4px 12px", background: "#2a2a3e", color: "#888",
            border: "none", borderRadius: 4, cursor: "pointer", fontSize: 12,
          }}>Refresh</button>
          <button onClick={handleToggle} style={{
            padding: "4px 12px",
            background: collecting ? "#ef4444" : "#22c55e",
            color: "#fff", border: "none", borderRadius: 4, cursor: "pointer", fontSize: 12,
          }}>
            {collecting ? "⏹ Stop Collector" : "▶ Start Collector"}
          </button>
          {collecting && <span style={{ fontSize: 10, color: "#22c55e" }}>● Collecting every 5min</span>}
        </div>
      </div>
      <div style={{ maxHeight: 550, overflowY: "auto" }}>
        {loading ? <div style={{ color: "#888" }}>Loading...</div> :
          news.map((n, i) => (
            <div key={i} style={{ borderBottom: "1px solid #222", padding: "8px 0" }}>
              <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 4 }}>
                <span style={{
                  fontSize: 10, background: sourceColor(n.source) + "22",
                  color: sourceColor(n.source), padding: "2px 6px", borderRadius: 4,
                }}>
                  {n.source}
                </span>
                <span style={{ fontSize: 10, color: "#555" }}>
                  {n.timestamp ? new Date(n.timestamp).toLocaleString() : ""}
                </span>
              </div>
              <div style={{ fontSize: 13, color: "#e0e0e0" }}>
                {n.url ? (
                  <a href={n.url} target="_blank" rel="noreferrer" style={{ color: "#e0e0e0", textDecoration: "none" }}>
                    {n.headline}
                  </a>
                ) : n.headline}
              </div>
            </div>
          ))
        }
      </div>
    </div>
  );
}
