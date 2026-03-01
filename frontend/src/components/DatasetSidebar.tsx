import type { TableInfo } from "../api/client";

interface Props {
  tables: TableInfo[];
  onAddDataset: () => void;
}

export default function DatasetSidebar({ tables, onAddDataset }: Props) {
  return (
    <div style={styles.sidebar}>
      <div style={styles.header}>
        <h3 style={styles.title}>Loaded Tables</h3>
        <button onClick={onAddDataset} style={styles.addBtn}>
          + Add Dataset
        </button>
      </div>
      {tables.map((t) => (
        <div key={t.name} style={styles.tableCard}>
          <div style={styles.tableName}>{t.name}</div>
          <div style={styles.rowCount}>
            {t.row_count.toLocaleString()} rows &middot;{" "}
            {t.columns.length} fields
          </div>
          <details style={styles.details}>
            <summary style={styles.summary}>Show fields</summary>
            <div style={styles.columns}>
              {t.columns.map((c) => (
                <span key={c.name} style={styles.col}>
                  {c.name}{" "}
                  <span style={styles.colType}>{c.type}</span>
                </span>
              ))}
            </div>
          </details>
        </div>
      ))}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  sidebar: {
    width: 240,
    background: "#f8fafc",
    borderRight: "1px solid #e5e7eb",
    padding: "1rem",
    overflowY: "auto",
    flexShrink: 0,
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: "0.75rem",
  },
  title: { fontSize: "0.9rem", fontWeight: 600 },
  addBtn: {
    padding: "2px 8px",
    background: "#2563eb",
    color: "#fff",
    border: "none",
    borderRadius: "4px",
    fontSize: "0.75rem",
    cursor: "pointer",
  },
  tableCard: {
    background: "#fff",
    borderRadius: "6px",
    padding: "0.6rem",
    marginBottom: "0.5rem",
    border: "1px solid #e5e7eb",
  },
  tableName: { fontWeight: 600, fontSize: "0.85rem", fontFamily: "monospace" },
  rowCount: { fontSize: "0.75rem", color: "#888", marginBottom: "0.25rem" },
  details: { marginTop: "0.25rem" },
  summary: {
    fontSize: "0.75rem",
    color: "#2563eb",
    cursor: "pointer",
    userSelect: "none",
  },
  columns: {
    display: "flex",
    flexDirection: "column",
    gap: "2px",
    marginTop: "0.35rem",
    paddingLeft: "0.25rem",
  },
  col: { fontSize: "0.75rem", fontFamily: "monospace" },
  colType: { color: "#888", fontSize: "0.7rem" },
};
