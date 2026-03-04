import { useState } from "react";
import type { DataQualityReport as DQReport } from "../api/client";

interface Props {
  report: DQReport;
}

const SEVERITY_COLORS = {
  error: { bg: "#fef2f2", text: "#991b1b", border: "#fecaca" },
  warning: { bg: "#fffbeb", text: "#92400e", border: "#fde68a" },
  info: { bg: "#eff6ff", text: "#1e40af", border: "#bfdbfe" },
} as const;

const DEFAULT_SEV = SEVERITY_COLORS.info;

const SEVERITY_LABELS: Record<string, string> = {
  error: "Error",
  warning: "Warning",
  info: "Info",
};

function ScoreBadge({ score }: { score: number }) {
  let color: string;
  let label: string;
  if (score >= 90) {
    color = "#16a34a";
    label = "Excellent";
  } else if (score >= 75) {
    color = "#2563eb";
    label = "Good";
  } else if (score >= 50) {
    color = "#d97706";
    label = "Fair";
  } else {
    color = "#dc2626";
    label = "Poor";
  }

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.35rem",
        background: color,
        color: "#fff",
        padding: "0.15rem 0.6rem",
        borderRadius: "12px",
        fontSize: "0.78rem",
        fontWeight: 600,
      }}
    >
      {score}% {label}
    </span>
  );
}

function MissingBar({ pct }: { pct: number }) {
  const filled = Math.min(100, pct);
  let color = "#16a34a";
  if (pct > 50) color = "#dc2626";
  else if (pct > 20) color = "#d97706";
  else if (pct > 0) color = "#2563eb";

  return (
    <div
      style={{
        width: 60,
        height: 6,
        background: "#e5e7eb",
        borderRadius: 3,
        overflow: "hidden",
        display: "inline-block",
        verticalAlign: "middle",
      }}
    >
      <div
        style={{
          width: `${filled}%`,
          height: "100%",
          background: color,
          borderRadius: 3,
        }}
      />
    </div>
  );
}

export default function DataQualityReport({ report }: Props) {
  const [expanded, setExpanded] = useState(true);
  const [showColumns, setShowColumns] = useState(false);

  const columnsWithIssues = report.columns.filter(
    (c) => c.issues && c.issues.length > 0,
  );

  return (
    <div style={styles.container}>
      {/* Header — always visible */}
      <button
        onClick={() => setExpanded(!expanded)}
        style={styles.header}
      >
        <div style={styles.headerLeft}>
          <span style={styles.headerIcon}>{expanded ? "\u25BC" : "\u25B6"}</span>
          <span style={styles.headerTitle}>Data Quality Report</span>
          <ScoreBadge score={report.overall_score} />
        </div>
        <div style={styles.headerRight}>
          <span style={styles.stat}>
            {report.row_count.toLocaleString()} rows
          </span>
          <span style={styles.statSep}>/</span>
          <span style={styles.stat}>
            {report.column_count} columns
          </span>
          <span style={styles.statSep}>/</span>
          <span style={styles.stat}>
            {report.completeness_pct}% complete
          </span>
        </div>
      </button>

      {expanded && (
        <div style={styles.body}>
          {/* Summary */}
          <p style={styles.summary}>{report.summary}</p>

          {/* Findings */}
          {report.findings.length > 0 && (
            <div style={styles.findings}>
              {report.findings.map((f, i) => {
                const sev = SEVERITY_COLORS[f.severity as keyof typeof SEVERITY_COLORS] ?? DEFAULT_SEV;
                return (
                  <div
                    key={i}
                    style={{
                      ...styles.finding,
                      background: sev.bg,
                      borderColor: sev.border,
                      color: sev.text,
                    }}
                  >
                    <span style={styles.findingSeverity}>
                      {SEVERITY_LABELS[f.severity] || f.severity}
                    </span>
                    {f.message}
                  </div>
                );
              })}
            </div>
          )}

          {report.findings.length === 0 && (
            <div style={styles.noIssues}>
              No data quality issues detected.
            </div>
          )}

          {/* Duplicate row info */}
          {report.duplicate_rows > 0 && (
            <div style={styles.dupInfo}>
              Duplicate row groups: {report.duplicate_rows}
            </div>
          )}

          {/* Column detail toggle */}
          {report.columns.length > 0 && (
            <div>
              <button
                onClick={() => setShowColumns(!showColumns)}
                style={styles.columnToggle}
              >
                {showColumns ? "Hide" : "Show"} column details
                {columnsWithIssues.length > 0 &&
                  ` (${columnsWithIssues.length} with issues)`}
              </button>

              {showColumns && (
                <div style={styles.columnTable}>
                  <table style={styles.table}>
                    <thead>
                      <tr>
                        <th style={styles.th}>Column</th>
                        <th style={styles.th}>Type</th>
                        <th style={styles.th}>Missing</th>
                        <th style={styles.th}>Distinct</th>
                        <th style={styles.th}>Issues</th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.columns.map((col, i) => (
                        <tr
                          key={i}
                          style={
                            col.issues.length > 0
                              ? styles.issueRow
                              : undefined
                          }
                        >
                          <td style={styles.td}>{col.name}</td>
                          <td style={styles.tdType}>{col.type}</td>
                          <td style={styles.td}>
                            {col.missing_pct !== undefined ? (
                              <>
                                <MissingBar pct={col.missing_pct} />{" "}
                                <span style={styles.pct}>
                                  {col.missing_pct}%
                                </span>
                              </>
                            ) : (
                              "-"
                            )}
                          </td>
                          <td style={styles.td}>
                            {col.distinct_count?.toLocaleString() ?? "-"}
                          </td>
                          <td style={styles.td}>
                            {col.issues.length > 0 ? (
                              <span style={styles.issueTags}>
                                {col.issues.map((issue) => (
                                  <span key={issue} style={styles.issueTag}>
                                    {issue.replace(/_/g, " ")}
                                  </span>
                                ))}
                              </span>
                            ) : (
                              <span style={styles.ok}>OK</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    background: "#fff",
    borderRadius: "10px",
    border: "1px solid #e5e7eb",
    marginBottom: "1rem",
    overflow: "hidden",
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    width: "100%",
    padding: "0.7rem 1rem",
    background: "#f8fafc",
    border: "none",
    borderBottom: "1px solid #e5e7eb",
    cursor: "pointer",
    fontFamily: "inherit",
    fontSize: "inherit",
  },
  headerLeft: {
    display: "flex",
    alignItems: "center",
    gap: "0.5rem",
  },
  headerIcon: {
    fontSize: "0.7rem",
    color: "#64748b",
  },
  headerTitle: {
    fontWeight: 600,
    fontSize: "0.9rem",
    color: "#1e293b",
  },
  headerRight: {
    display: "flex",
    alignItems: "center",
    gap: "0.15rem",
    fontSize: "0.8rem",
    color: "#64748b",
  },
  stat: {},
  statSep: { color: "#cbd5e1", margin: "0 0.15rem" },
  body: {
    padding: "0.8rem 1rem",
  },
  summary: {
    fontSize: "0.88rem",
    color: "#334155",
    margin: "0 0 0.7rem 0",
  },
  findings: {
    display: "flex",
    flexDirection: "column",
    gap: "0.4rem",
    marginBottom: "0.7rem",
  },
  finding: {
    padding: "0.4rem 0.65rem",
    borderRadius: "6px",
    fontSize: "0.82rem",
    border: "1px solid",
    lineHeight: 1.4,
  },
  findingSeverity: {
    fontWeight: 600,
    marginRight: "0.4rem",
    textTransform: "uppercase" as const,
    fontSize: "0.7rem",
    letterSpacing: "0.03em",
  },
  noIssues: {
    fontSize: "0.85rem",
    color: "#16a34a",
    marginBottom: "0.5rem",
  },
  dupInfo: {
    fontSize: "0.82rem",
    color: "#64748b",
    marginBottom: "0.5rem",
  },
  columnToggle: {
    background: "none",
    border: "none",
    color: "#2563eb",
    cursor: "pointer",
    fontSize: "0.82rem",
    padding: 0,
    fontFamily: "inherit",
    textDecoration: "underline",
    marginBottom: "0.5rem",
  },
  columnTable: {
    overflowX: "auto",
    marginTop: "0.5rem",
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
    fontSize: "0.8rem",
  },
  th: {
    textAlign: "left",
    padding: "0.35rem 0.5rem",
    borderBottom: "2px solid #e5e7eb",
    fontWeight: 600,
    color: "#475569",
    fontSize: "0.75rem",
    textTransform: "uppercase" as const,
    letterSpacing: "0.03em",
  },
  td: {
    padding: "0.3rem 0.5rem",
    borderBottom: "1px solid #f1f5f9",
    verticalAlign: "middle",
  },
  tdType: {
    padding: "0.3rem 0.5rem",
    borderBottom: "1px solid #f1f5f9",
    fontFamily: "monospace",
    fontSize: "0.75rem",
    color: "#64748b",
  },
  pct: {
    fontSize: "0.75rem",
    color: "#64748b",
  },
  issueRow: {
    background: "#fffbeb",
  },
  issueTags: {
    display: "flex",
    gap: "0.25rem",
    flexWrap: "wrap",
  },
  issueTag: {
    background: "#fef3c7",
    color: "#92400e",
    padding: "0.1rem 0.4rem",
    borderRadius: "4px",
    fontSize: "0.7rem",
    fontWeight: 500,
  },
  ok: {
    color: "#16a34a",
    fontSize: "0.78rem",
  },
};
