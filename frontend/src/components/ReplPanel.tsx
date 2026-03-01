import { useState } from "react";
import Editor from "@monaco-editor/react";
import PlotlyChart from "./PlotlyChart";

interface Props {
  onExecute: (code: string, language: string) => Promise<Record<string, unknown>>;
  loading: boolean;
}

export default function ReplPanel({ onExecute, loading }: Props) {
  const [language, setLanguage] = useState<"python" | "sql">("sql");
  const [code, setCode] = useState(language === "sql" ? "SELECT * FROM " : "# Use df, px, go\n");
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  const handleRun = async () => {
    if (!code.trim() || loading) return;
    const res = await onExecute(code, language);
    setResult(res);
  };

  const toggleLang = (lang: "python" | "sql") => {
    setLanguage(lang);
    setCode(lang === "sql" ? "SELECT * FROM " : "# Use df, px, go\n");
    setResult(null);
  };

  return (
    <div style={styles.container}>
      <div style={styles.toolbar}>
        <div style={styles.tabs}>
          <button
            onClick={() => toggleLang("sql")}
            style={language === "sql" ? styles.activeTab : styles.tab}
          >
            SQL
          </button>
          <button
            onClick={() => toggleLang("python")}
            style={language === "python" ? styles.activeTab : styles.tab}
          >
            Python
          </button>
        </div>
        <button onClick={handleRun} disabled={loading} style={styles.runBtn}>
          {loading ? "Running..." : "Run"}
        </button>
      </div>
      <div style={styles.editor}>
        <Editor
          height="150px"
          language={language}
          value={code}
          onChange={(v) => setCode(v || "")}
          theme="vs-dark"
          options={{
            minimap: { enabled: false },
            fontSize: 13,
            lineNumbers: "on",
            scrollBeyondLastLine: false,
            wordWrap: "on",
          }}
        />
      </div>
      {result && (
        <div style={styles.output}>
          {(result.error as string) && (
            <pre style={styles.error}>{result.error as string}</pre>
          )}
          {(result.stdout as string) && (
            <pre style={styles.stdout}>{result.stdout as string}</pre>
          )}
          {(result.figures as Record<string, unknown>[])?.map((fig, i) => (
            <PlotlyChart key={i} spec={fig} />
          ))}
          {(result.data_table as Record<string, unknown>[]) && (
            <div style={styles.tableWrap}>
              <table style={styles.table}>
                <thead>
                  <tr>
                    {(result.columns as string[])?.map((col) => (
                      <th key={col} style={styles.th}>{col}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(result.data_table as Record<string, unknown>[]).slice(0, 50).map((row, ri) => (
                    <tr key={ri}>
                      {(result.columns as string[])?.map((col) => (
                        <td key={col} style={styles.td}>{String(row[col] ?? "")}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    borderTop: "1px solid #e5e7eb",
    background: "#1e293b",
    color: "#e2e8f0",
  },
  toolbar: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "0.4rem 0.75rem",
    background: "#0f172a",
  },
  tabs: { display: "flex", gap: "0.25rem" },
  tab: {
    padding: "0.3rem 0.7rem",
    background: "transparent",
    color: "#94a3b8",
    border: "none",
    borderRadius: "4px",
    cursor: "pointer",
    fontSize: "0.8rem",
  },
  activeTab: {
    padding: "0.3rem 0.7rem",
    background: "#334155",
    color: "#fff",
    border: "none",
    borderRadius: "4px",
    cursor: "pointer",
    fontSize: "0.8rem",
    fontWeight: 600,
  },
  runBtn: {
    padding: "0.3rem 0.8rem",
    background: "#22c55e",
    color: "#fff",
    border: "none",
    borderRadius: "4px",
    fontSize: "0.8rem",
    fontWeight: 600,
    cursor: "pointer",
  },
  editor: { borderBottom: "1px solid #334155" },
  output: {
    maxHeight: 300,
    overflowY: "auto",
    padding: "0.5rem 0.75rem",
  },
  error: { color: "#f87171", fontSize: "0.8rem", whiteSpace: "pre-wrap" },
  stdout: { color: "#a3e635", fontSize: "0.8rem", whiteSpace: "pre-wrap" },
  tableWrap: { overflowX: "auto", marginTop: "0.5rem" },
  table: { borderCollapse: "collapse", fontSize: "0.8rem", width: "100%" },
  th: {
    background: "#334155",
    padding: "4px 8px",
    border: "1px solid #475569",
    textAlign: "left",
    fontWeight: 600,
  },
  td: { padding: "4px 8px", border: "1px solid #475569" },
};
