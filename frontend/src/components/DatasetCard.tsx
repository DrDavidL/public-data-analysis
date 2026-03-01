import type { DatasetResult } from "../api/client";

const SOURCE_COLORS: Record<string, string> = {
  "data.gov": "#0071bc",
  worldbank: "#009fda",
  kaggle: "#20beff",
  huggingface: "#ff9d00",
  sdohplace: "#4caf50",
  cms: "#d63384",
  harvard_dataverse: "#a51c30",
};

interface Props {
  dataset: DatasetResult;
  onSelect: (dataset: DatasetResult) => void;
  disabled?: boolean;
}

export default function DatasetCard({ dataset, onSelect, disabled }: Props) {
  const badgeColor = SOURCE_COLORS[dataset.source] || "#888";

  return (
    <div style={styles.card}>
      <div style={styles.header}>
        <span style={{ ...styles.badge, background: badgeColor }}>
          {dataset.source}
        </span>
        <span style={styles.formats}>
          {dataset.formats.slice(0, 3).join(", ")}
        </span>
      </div>
      <h3 style={styles.title}>{dataset.title}</h3>
      <p style={styles.desc}>
        {dataset.ai_description || dataset.description}
      </p>
      {dataset.ai_description && dataset.description && (
        <details style={styles.details}>
          <summary style={styles.summary}>Original description</summary>
          <p style={styles.origDesc}>{dataset.description}</p>
        </details>
      )}
      <button
        onClick={() => onSelect(dataset)}
        disabled={disabled || !dataset.download_url}
        style={{
          ...styles.selectBtn,
          opacity: disabled || !dataset.download_url ? 0.5 : 1,
        }}
      >
        {dataset.download_url ? "Select & Analyze" : "No download available"}
      </button>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  card: {
    background: "#fff",
    borderRadius: "10px",
    padding: "1.25rem",
    boxShadow: "0 1px 6px rgba(0,0,0,0.07)",
    display: "flex",
    flexDirection: "column",
    gap: "0.5rem",
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
  },
  badge: {
    color: "#fff",
    padding: "2px 8px",
    borderRadius: "4px",
    fontSize: "0.75rem",
    fontWeight: 600,
  },
  formats: { fontSize: "0.75rem", color: "#888" },
  title: { fontSize: "1rem", fontWeight: 600, lineHeight: 1.3 },
  desc: { fontSize: "0.85rem", color: "#444", lineHeight: 1.5, flex: 1 },
  details: { fontSize: "0.8rem" },
  summary: { cursor: "pointer", color: "#666" },
  origDesc: { color: "#666", marginTop: "0.25rem", lineHeight: 1.4 },
  selectBtn: {
    marginTop: "0.5rem",
    padding: "0.5rem",
    background: "#2563eb",
    color: "#fff",
    border: "none",
    borderRadius: "6px",
    fontSize: "0.85rem",
    fontWeight: 600,
    cursor: "pointer",
  },
};
