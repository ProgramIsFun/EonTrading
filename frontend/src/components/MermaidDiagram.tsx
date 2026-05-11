import { useEffect, useRef, useState } from "react";
import mermaid from "mermaid";

mermaid.initialize({
  theme: "dark",
  themeVariables: {
    primaryColor: "#1a2a4a",
    primaryBorderColor: "#818cf8",
    primaryTextColor: "#e0e0e0",
    lineColor: "#818cf8",
    secondaryColor: "#1a3a2a",
    tertiaryColor: "#2a1a2a",
    fontSize: "13px",
  },
  flowchart: { useMaxWidth: true, htmlLabels: true },
});

let idCounter = 0;

export default function MermaidDiagram({ chart }: { chart: string }) {
  const [svg, setSvg] = useState("");
  const id = useRef(`mermaid-${++idCounter}`);

  useEffect(() => {
    mermaid.render(id.current, chart).then(({ svg }) => setSvg(svg));
  }, [chart]);

  return <div style={{ textAlign: "center", overflowX: "auto" }} dangerouslySetInnerHTML={{ __html: svg }} />;
}
