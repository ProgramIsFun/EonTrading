const TAILON_PORT = 8001;

export default function LogViewer() {
  const url = `http://localhost:${TAILON_PORT}`;

  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 12, alignItems: "center" }}>
        <span style={{ fontSize: 13, color: "#888" }}>Component Logs</span>
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          style={{ fontSize: 11, color: "#818cf8", textDecoration: "none" }}
        >
          Open in tailon ↗
        </a>
      </div>
      <iframe
        src={url}
        style={{
          width: "100%",
          height: 600,
          border: "1px solid #2a2a3e",
          borderRadius: 8,
          background: "#1e1e2e",
        }}
        title="Log Viewer"
      />
    </div>
  );
}
