import { useEffect, useState } from "react";
import { fetchNews } from "../hooks/api";

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

  useEffect(() => {
    fetchNews().then(setNews).finally(() => setLoading(false));
  }, []);

  const sourceColor = (s: string) => {
    if (s.startsWith("reddit")) return "#ff4500";
    if (s === "rss") return "#f59e0b";
    return "#818cf8";
  };

  if (loading) return <div style={{ color: "#888", padding: 16 }}>Loading news...</div>;

  return (
    <div style={{ background: "#1e1e2e", borderRadius: 8, padding: 16, maxHeight: 600, overflowY: "auto" }}>
      <div style={{ fontSize: 14, color: "#888", marginBottom: 12 }}>
        News Feed ({news.length} articles)
      </div>
      {news.map((n, i) => (
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
      ))}
    </div>
  );
}
