import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useLocation, useNavigate } from "react-router-dom";
import { analysisApi, sessionsApi, type AnalysisResponse, type TableInfo, type DataQualityReport as DQReport } from "../api/client";
import PlotlyChart, { type ChartMeta } from "../components/PlotlyChart";
import ChatPanel from "../components/ChatPanel";
import ReplPanel from "../components/ReplPanel";
import DatasetSidebar from "../components/DatasetSidebar";
import DataQualityReport from "../components/DataQualityReport";
import SessionHistory from "../components/SessionHistory";

interface Message {
  role: "user" | "assistant";
  content: string;
  sqlExecuted?: string;
  codeExecuted?: string;
  suggestions?: string[];
}

interface ChartWithCode {
  spec: Record<string, unknown>;
  sourceCode?: string;
}

interface DataTableResult {
  data: Record<string, unknown>[];
  columns: string[];
  question: string;
}

interface LocationState {
  question: string;
  startResponse: {
    session_id: string;
    table_name: string;
    columns: { name: string; type: string }[];
    row_count: number;
    data_quality?: DQReport;
    charts: Record<string, unknown>[];
    chart_code?: string | null;
  };
  datasetTitle: string;
  datasetDescription?: string;
  datasetSource?: string;
  downloadUrl?: string | null;
  restoredChatHistory?: { role: string; content: string; code_executed?: string; sql_executed?: string }[];
}

export default function AnalysisPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const state = location.state as LocationState | null;

  const [charts, setCharts] = useState<ChartWithCode[]>(
    () => (state?.startResponse.charts || []).map((spec) => ({
      spec,
      sourceCode: state?.startResponse.chart_code || undefined,
    })),
  );
  const [messages, setMessages] = useState<Message[]>([]);
  const [tables, setTables] = useState<TableInfo[]>([]);
  const [dataTables, setDataTables] = useState<DataTableResult[]>([]);
  const [askLoading, setAskLoading] = useState(false);
  const [replLoading, setReplLoading] = useState(false);
  const [showRepl, setShowRepl] = useState(false);
  const [pinnedIndices, setPinnedIndices] = useState<Set<number>>(new Set());
  const [dashboardView, setDashboardView] = useState(false);

  useEffect(() => {
    if (!sessionId) return;
    // Load initial table info
    analysisApi.tables(sessionId).then((res) => {
      setTables(res.data.tables);
    }).catch(() => {});

    // Add initial context message
    if (state) {
      const desc = state.datasetDescription
        ? `\n\n${state.datasetDescription}`
        : "";
      const chartsNote =
        state.startResponse.charts.length > 0
          ? " I've generated some preliminary charts."
          : "";
      const welcomeMsg: Message = {
        role: "assistant",
        content: `Loaded "${state.datasetTitle}" (${state.startResponse.row_count.toLocaleString()} rows, ${state.startResponse.columns.length} columns).${chartsNote} Ask me anything about this data!${desc}`,
        suggestions: [
          "Summarize the key trends",
          "Show me the distribution of values",
          "What are the top 10 entries?",
        ],
      };

      // Restore prior chat history if reloading a saved session
      if (state.restoredChatHistory && state.restoredChatHistory.length > 0) {
        const restored: Message[] = state.restoredChatHistory.map((m) => ({
          role: m.role as "user" | "assistant",
          content: m.content,
          codeExecuted: m.code_executed || undefined,
          sqlExecuted: m.sql_executed || undefined,
        }));
        setMessages([welcomeMsg, ...restored]);
      } else {
        setMessages([welcomeMsg]);
      }
    }
  }, [sessionId, state]);

  const handleAsk = useCallback(
    async (question: string): Promise<AnalysisResponse> => {
      if (!sessionId) throw new Error("No session");

      setMessages((prev) => [...prev, { role: "user", content: question }]);
      setAskLoading(true);

      try {
        const res = await analysisApi.ask({
          session_id: sessionId,
          question,
        });
        const r = res.data;

        // Build a concise chat message; heavy content goes to main panel
        const hasCharts = r.charts && r.charts.length > 0;
        const hasTable = r.data_table && r.data_table.data.length > 0;
        const notes: string[] = [];
        if (hasCharts) notes.push(`${r.charts!.length} chart(s) added`);
        if (hasTable) notes.push(`data table added (${r.data_table!.data.length} rows)`);
        const suffix = notes.length
          ? `\n\n[${notes.join("; ")} — see main panel]`
          : "";

        const assistantMsg: Message = {
          role: "assistant",
          content: (r.text_answer || "Here are the results.") + suffix,
          sqlExecuted: r.sql_executed || undefined,
          codeExecuted: r.code_executed || undefined,
          suggestions: r.follow_up_suggestions,
        };

        setMessages((prev) => [...prev, assistantMsg]);

        // Add charts to the main panel
        if (hasCharts) {
          const code = r.code_executed || r.sql_executed || undefined;
          setCharts((prev) => [
            ...prev,
            ...r.charts!.map((spec) => ({ spec, sourceCode: code })),
          ]);
        }

        // Add data table to the main panel
        if (hasTable) {
          setDataTables((prev) => [
            ...prev,
            { data: r.data_table!.data, columns: r.data_table!.columns, question },
          ]);
        }

        return r;
      } finally {
        setAskLoading(false);
      }
    },
    [sessionId],
  );

  const handleExecute = useCallback(
    async (code: string, language: string): Promise<Record<string, unknown>> => {
      if (!sessionId) throw new Error("No session");
      setReplLoading(true);
      try {
        const res = await analysisApi.execute(sessionId, code, language);
        // Add any figures to chart area
        const figs = res.data.figures as Record<string, unknown>[] | undefined;
        if (figs && figs.length > 0) {
          setCharts((prev) => [
            ...prev,
            ...figs.map((spec) => ({ spec, sourceCode: code })),
          ]);
        }
        return res.data;
      } finally {
        setReplLoading(false);
      }
    },
    [sessionId],
  );

  const handleAddDataset = () => {
    navigate("/search");
  };

  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sidebarWidth, setSidebarWidth] = useState(220);
  const dragging = useRef(false);

  const onResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragging.current = true;
    const startX = e.clientX;
    const startW = sidebarWidth;
    const onMove = (ev: MouseEvent) => {
      if (!dragging.current) return;
      const newW = Math.min(400, Math.max(140, startW + ev.clientX - startX));
      setSidebarWidth(newW);
    };
    const onUp = () => {
      dragging.current = false;
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }, [sidebarWidth]);

  const [reloading, setReloading] = useState(false);
  const handleReload = async (savedSessionId: string) => {
    setReloading(true);
    try {
      const res = await sessionsApi.reload(savedSessionId);
      const r = res.data;
      navigate(`/analysis/${r.session_id}`, {
        state: {
          question: r.chat_history?.[0]?.content || "",
          startResponse: {
            session_id: r.session_id,
            table_name: r.table_name,
            columns: r.columns,
            row_count: r.row_count,
            data_quality: r.data_quality,
            charts: r.charts,
            chart_code: r.chart_code,
          },
          datasetTitle: r.dataset_title,
          datasetDescription: r.dataset_description,
          datasetSource: r.dataset_source || "",
          downloadUrl: r.download_url || null,
          restoredChatHistory: r.chat_history,
        },
      });
    } catch {
      // Show error in chat
      setMessages((prev) => [...prev, {
        role: "assistant",
        content: "Failed to reload session. The dataset may no longer be available.",
      }]);
    } finally {
      setReloading(false);
    }
  };

  return (
    <div style={styles.page}>
      <header style={styles.header}>
        <button onClick={() => navigate("/search")} style={styles.backBtn}>
          &larr; New Search
        </button>
        <h1 style={styles.title}>
          {state?.datasetTitle || "Analysis"}
        </h1>
        <a
          href="https://docs.google.com/forms/d/e/1FAIpQLSdM6pWM7cQ2dKRpwKABo918d60IYnujGUkgsmd1A5moCBj_gQ/viewform?usp=header"
          target="_blank"
          rel="noopener noreferrer"
          style={styles.feedbackLink}
        >
          Feedback
        </a>
        {pinnedIndices.size > 0 && (
          <button
            onClick={() => setDashboardView(!dashboardView)}
            style={{
              ...styles.replToggle,
              background: dashboardView ? "#2563eb" : "#1e293b",
            }}
          >
            {dashboardView ? "Exit Dashboard" : `Dashboard (${pinnedIndices.size})`}
          </button>
        )}
        <button
          onClick={() => setShowRepl(!showRepl)}
          style={styles.replToggle}
        >
          {showRepl ? "Hide REPL" : "Show REPL"}
        </button>
      </header>

      <div style={styles.body}>
        {sidebarOpen && (
          <>
            <div style={{ ...styles.leftSidebar, width: sidebarWidth }}>
              <SessionHistory onReload={handleReload} loading={reloading} />
              <DatasetSidebar tables={tables} onAddDataset={handleAddDataset} />
            </div>
            <div
              onMouseDown={onResizeStart}
              onMouseEnter={(e) => { e.currentTarget.style.background = "#3b82f6"; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = "#e5e7eb"; }}
              style={styles.resizeHandle}
            />
          </>
        )}
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          style={styles.sidebarToggle}
          title={sidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
        >
          {sidebarOpen ? "\u2039" : "\u203A"}
        </button>

        <div style={styles.mainArea}>
          {/* Charts area */}
          <div style={styles.chartsArea}>
            {/* Data Quality Report — shown above charts */}
            {state?.startResponse.data_quality &&
              state.startResponse.data_quality.columns?.length > 0 && (
                <DataQualityReport report={state.startResponse.data_quality} />
              )}

            {state?.downloadUrl && (
              <div style={styles.downloadLink}>
                <a href={state.downloadUrl} target="_blank" rel="noopener noreferrer" style={styles.downloadAnchor}>
                  Download original dataset
                </a>
              </div>
            )}

            {charts.length === 0 && dataTables.length === 0 ? (
              <div style={styles.placeholder}>
                Charts and results will appear here as you explore the data.
              </div>
            ) : (
              <>
                {dashboardView && (
                  <div style={styles.dashboardHeader}>
                    <h2 style={styles.dashboardTitle}>Dashboard</h2>
                    <span style={styles.dashboardSubtitle}>
                      {pinnedIndices.size} pinned chart{pinnedIndices.size !== 1 ? "s" : ""} from &ldquo;{state?.datasetTitle}&rdquo;
                    </span>
                  </div>
                )}
                <div style={styles.chartsGrid}>
                  {charts.map((chart, i) => {
                    if (dashboardView && !pinnedIndices.has(i)) return null;
                    const chartMeta: ChartMeta = {
                      dataSource: state?.datasetSource,
                      datasetTitle: state?.datasetTitle,
                      rowCount: state?.startResponse.row_count,
                    };
                    return (
                      <PlotlyChart
                        key={i}
                        spec={chart.spec}
                        sourceCode={chart.sourceCode}
                        meta={chartMeta}
                        pinned={pinnedIndices.has(i)}
                        onTogglePin={() => {
                          setPinnedIndices((prev) => {
                            const next = new Set(prev);
                            if (next.has(i)) next.delete(i);
                            else next.add(i);
                            return next;
                          });
                        }}
                      />
                    );
                  })}
                </div>

                {/* Data tables from Q&A */}
                {dataTables.map((dt, i) => (
                  <div key={`dt-${i}`} style={styles.dataTableCard}>
                    <div style={styles.dataTableHeader}>
                      <span style={styles.dataTableTitle}>{dt.question}</span>
                      <span style={styles.dataTableMeta}>
                        {dt.data.length} row{dt.data.length !== 1 ? "s" : ""} &middot; {dt.columns.length} column{dt.columns.length !== 1 ? "s" : ""}
                      </span>
                    </div>
                    <div style={styles.dataTableWrap}>
                      <table style={styles.dataTable}>
                        <thead>
                          <tr>
                            {dt.columns.map((col) => (
                              <th key={col} style={styles.dtTh}>{col}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {dt.data.slice(0, 50).map((row, ri) => (
                            <tr key={ri}>
                              {dt.columns.map((col) => (
                                <td key={col} style={styles.dtTd}>
                                  {String(row[col] ?? "")}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {dt.data.length > 50 && (
                        <p style={styles.dtTruncated}>
                          Showing 50 of {dt.data.length} rows
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </>
            )}
          </div>

          {/* REPL Panel */}
          {showRepl && (
            <ReplPanel onExecute={handleExecute} loading={replLoading} />
          )}
        </div>

        {/* Chat Panel */}
        <div style={styles.chatArea}>
          <ChatPanel
            messages={messages}
            onAsk={handleAsk}
            loading={askLoading}
          />
        </div>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  page: { height: "100vh", display: "flex", flexDirection: "column" },
  header: {
    display: "flex",
    alignItems: "center",
    gap: "1rem",
    padding: "0.6rem 1rem",
    background: "#fff",
    borderBottom: "1px solid #e5e7eb",
  },
  backBtn: {
    background: "none",
    border: "1px solid #ddd",
    borderRadius: "6px",
    padding: "0.3rem 0.7rem",
    cursor: "pointer",
    fontSize: "0.85rem",
  },
  title: { flex: 1, fontSize: "1rem", fontWeight: 600 },
  feedbackLink: {
    color: "#6b7280",
    fontSize: "0.82rem",
    textDecoration: "none",
  },
  replToggle: {
    padding: "0.3rem 0.7rem",
    background: "#1e293b",
    color: "#fff",
    border: "none",
    borderRadius: "6px",
    fontSize: "0.8rem",
    cursor: "pointer",
  },
  body: { flex: 1, display: "flex", overflow: "hidden" },
  leftSidebar: {
    display: "flex",
    flexDirection: "column",
    flexShrink: 0,
    overflow: "hidden",
    minWidth: 0,
  },
  resizeHandle: {
    width: 4,
    cursor: "col-resize",
    background: "#e5e7eb",
    flexShrink: 0,
    transition: "background 0.15s",
  },
  sidebarToggle: {
    display: "flex",
    alignItems: "center",
    background: "#f1f5f9",
    border: "none",
    borderRight: "1px solid #e5e7eb",
    cursor: "pointer",
    padding: "0 3px",
    fontSize: "1rem",
    color: "#6b7280",
    flexShrink: 0,
  },
  mainArea: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
  },
  chartsArea: {
    flex: 1,
    overflowY: "auto",
    padding: "1rem",
    background: "#f8fafc",
  },
  placeholder: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    height: "100%",
    color: "#94a3b8",
    fontSize: "0.95rem",
  },
  chartsGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(2, 1fr)",
    gap: "1rem",
  },
  downloadLink: {
    marginBottom: "0.75rem",
    fontSize: "0.82rem",
  },
  downloadAnchor: {
    color: "#2563eb",
    textDecoration: "none",
  },
  chatArea: { width: 340, flexShrink: 0 },
  dashboardHeader: {
    marginBottom: "1rem",
    paddingBottom: "0.5rem",
    borderBottom: "1px solid #e2e8f0",
  },
  dashboardTitle: {
    fontSize: "1.1rem",
    fontWeight: 700,
    color: "#1e293b",
    margin: "0 0 0.25rem 0",
  },
  dashboardSubtitle: {
    fontSize: "0.8rem",
    color: "#64748b",
  },
  dataTableCard: {
    background: "#fff",
    border: "1px solid #e2e8f0",
    borderRadius: "8px",
    marginTop: "1rem",
    overflow: "hidden",
  },
  dataTableHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "0.6rem 0.75rem",
    background: "#f8fafc",
    borderBottom: "1px solid #e2e8f0",
  },
  dataTableTitle: {
    fontWeight: 600,
    fontSize: "0.85rem",
    color: "#1e293b",
  },
  dataTableMeta: {
    fontSize: "0.75rem",
    color: "#64748b",
  },
  dataTableWrap: {
    overflowX: "auto",
    maxHeight: 400,
    overflowY: "auto",
  },
  dataTable: {
    borderCollapse: "collapse",
    fontSize: "0.8rem",
    width: "100%",
  },
  dtTh: {
    position: "sticky" as const,
    top: 0,
    background: "#f1f5f9",
    padding: "6px 10px",
    borderBottom: "1px solid #e2e8f0",
    textAlign: "left" as const,
    fontWeight: 600,
    whiteSpace: "nowrap",
  },
  dtTd: {
    padding: "5px 10px",
    borderBottom: "1px solid #f1f5f9",
    whiteSpace: "nowrap",
  },
  dtTruncated: {
    fontSize: "0.75rem",
    color: "#888",
    padding: "0.4rem 0.75rem",
  },
};
