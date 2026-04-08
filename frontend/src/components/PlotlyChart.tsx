import { useState } from "react";
import Plot from "react-plotly.js";

export interface ChartMeta {
  dataSource?: string;
  datasetTitle?: string;
  rowCount?: number;
}

interface Props {
  spec: Record<string, unknown>;
  sourceCode?: string;
  meta?: ChartMeta;
  pinned?: boolean;
  onTogglePin?: () => void;
}

const SOURCE_LABELS: Record<string, string> = {
  "data.gov": "data.gov",
  worldbank: "World Bank",
  kaggle: "Kaggle",
  huggingface: "HuggingFace",
  sdohplace: "SDOH Place",
  cms: "CMS",
  harvard_dataverse: "Harvard Dataverse",
  hud: "HUD",
  bls: "BLS",
  fred: "FRED",
  cmap: "CMAP",
  census: "Census",
  owid: "Our World in Data",
  oecd: "OECD",
  vdem: "V-Dem",
  eia: "EIA",
  usaspending: "USASpending",
  cdc_places: "CDC PLACES",
  clinicaltrials: "ClinicalTrials.gov",
  openfda: "OpenFDA",
  cfpb: "CFPB",
  sec_edgar: "SEC EDGAR",
  federal_register: "Federal Register",
  epa_ghgrp: "EPA GHGRP",
  fdic: "FDIC",
  upload: "Upload",
};

export default function PlotlyChart({ spec, sourceCode, meta, pinned, onTogglePin }: Props) {
  const [showCode, setShowCode] = useState(false);
  const [copied, setCopied] = useState(false);

  const data = (spec.data || []) as Plotly.Data[];
  const specLayout = (spec.layout as Partial<Plotly.Layout>) || {};
  const title = specLayout.title;
  // Extract title text for display above the chart (supports wrapping)
  const titleText =
    typeof title === "string"
      ? title
      : typeof title === "object" && title !== null && "text" in title
        ? (title as { text?: string }).text || ""
        : "";
  const layout = {
    ...specLayout,
    // Remove title from Plotly (we render it ourselves for better wrapping)
    title: undefined,
    autosize: true,
    margin: { t: 20, r: 20, b: 40, l: 50 },
  };

  const handleCopy = async () => {
    if (!sourceCode) return;
    await navigator.clipboard.writeText(sourceCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div style={{ width: "100%", minHeight: 350, marginBottom: "1.5rem" }}>
      {titleText && <div style={styles.chartTitle}>{titleText}</div>}
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
      <div style={styles.chartActions}>
        {onTogglePin && (
          <button
            onClick={onTogglePin}
            style={{
              ...styles.pinBtn,
              ...(pinned ? styles.pinBtnActive : {}),
            }}
            title={pinned ? "Unpin from dashboard" : "Pin to dashboard"}
          >
            {pinned ? "Pinned" : "Pin to Dashboard"}
          </button>
        )}
      </div>
      {meta?.dataSource && (
        <div style={styles.metaBadge}>
          <span style={styles.metaLabel}>Source:</span>{" "}
          <span style={styles.metaValue}>{SOURCE_LABELS[meta.dataSource] || meta.dataSource}</span>
          {meta.rowCount != null && (
            <>
              <span style={styles.metaSep}>&middot;</span>
              <span style={styles.metaValue}>{meta.rowCount.toLocaleString()} rows</span>
            </>
          )}
        </div>
      )}
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
  chartTitle: {
    fontSize: "0.9rem",
    fontWeight: 600,
    color: "#1e293b",
    lineHeight: 1.35,
    padding: "0.25rem 0.25rem 0",
    wordWrap: "break-word",
    overflowWrap: "break-word",
  },
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
  chartActions: {
    display: "flex",
    alignItems: "center",
    gap: "0.4rem",
    marginTop: "0.5rem",
  },
  pinBtn: {
    background: "#f8fafc",
    border: "1px solid #cbd5e1",
    borderRadius: "4px",
    padding: "4px 12px",
    fontSize: "0.8rem",
    color: "#475569",
    cursor: "pointer",
  },
  pinBtnActive: {
    background: "#2563eb",
    color: "#fff",
    borderColor: "#2563eb",
  },
  metaBadge: {
    display: "flex",
    alignItems: "center",
    gap: "0.3rem",
    padding: "0.25rem 0.5rem",
    fontSize: "0.72rem",
    color: "#64748b",
    background: "#f1f5f9",
    borderRadius: "4px",
    marginTop: "0.25rem",
    width: "fit-content",
  },
  metaLabel: {
    fontWeight: 600,
    color: "#475569",
  },
  metaValue: {
    color: "#64748b",
  },
  metaSep: {
    color: "#cbd5e1",
    margin: "0 0.1rem",
  },
};
