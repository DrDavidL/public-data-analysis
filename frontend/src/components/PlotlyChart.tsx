import { useState } from "react";
import Plot from "react-plotly.js";

interface Props {
  spec: Record<string, unknown>;
  sourceCode?: string;
}

export default function PlotlyChart({ spec, sourceCode }: Props) {
  const [showCode, setShowCode] = useState(false);
  const [copied, setCopied] = useState(false);

  const data = (spec.data || []) as Plotly.Data[];
  const layout = {
    ...(spec.layout as Partial<Plotly.Layout> || {}),
    autosize: true,
    margin: { t: 60, r: 20, b: 40, l: 50 },
  };

  const handleCopy = async () => {
    if (!sourceCode) return;
    await navigator.clipboard.writeText(sourceCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div style={{ width: "100%", minHeight: 350 }}>
      <Plot
        data={data}
        layout={layout}
        config={{
          responsive: true,
          displayModeBar: true,
          modeBarButtonsToRemove: ["lasso2d", "select2d"],
          displaylogo: false,
        }}
        style={{ width: "100%", height: "100%" }}
        useResizeHandler
      />
      {sourceCode && (
        <div style={styles.codeSection}>
          <button onClick={() => setShowCode(!showCode)} style={styles.toggleBtn}>
            {showCode ? "Hide Code" : "Show Code"}
          </button>
          {showCode && (
            <div style={styles.codeWrapper}>
              <button onClick={handleCopy} style={styles.copyBtn}>
                {copied ? "Copied!" : "Copy"}
              </button>
              <pre style={styles.code}>{sourceCode}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  codeSection: {
    marginTop: "0.25rem",
  },
  toggleBtn: {
    background: "none",
    border: "1px solid #cbd5e1",
    borderRadius: "4px",
    padding: "2px 8px",
    fontSize: "0.75rem",
    color: "#475569",
    cursor: "pointer",
  },
  codeWrapper: {
    position: "relative",
    marginTop: "0.25rem",
  },
  copyBtn: {
    position: "absolute",
    top: "0.4rem",
    right: "0.4rem",
    background: "#334155",
    color: "#e2e8f0",
    border: "1px solid #475569",
    borderRadius: "4px",
    padding: "2px 8px",
    fontSize: "0.7rem",
    cursor: "pointer",
    zIndex: 1,
  },
  code: {
    background: "#1e293b",
    color: "#e2e8f0",
    padding: "0.75rem",
    borderRadius: "6px",
    overflow: "auto",
    fontSize: "0.78rem",
    maxHeight: "300px",
    lineHeight: 1.5,
  },
};
