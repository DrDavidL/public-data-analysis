import { useState, useEffect, useCallback } from "react";
import { useParams, useLocation, useNavigate } from "react-router-dom";
import { analysisApi, sessionsApi, type AnalysisResponse, type TableInfo, type DataQualityReport as DQReport } from "../api/client";
import PlotlyChart from "../components/PlotlyChart";
import ChatPanel from "../components/ChatPanel";
import ReplPanel from "../components/ReplPanel";
import DatasetSidebar from "../components/DatasetSidebar";
import DataQualityReport from "../components/DataQualityReport";
import SessionHistory from "../components/SessionHistory";

interface Message {
  role: "user" | "assistant";
  content: string;
  charts?: Record<string, unknown>[];
  dataTable?: { data: Record<string, unknown>[]; columns: string[] };
  sqlExecuted?: string;
  codeExecuted?: string;
  suggestions?: string[];
}

interface ChartWithCode {
  spec: Record<string, unknown>;
  sourceCode?: string;
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
  const [askLoading, setAskLoading] = useState(false);
  const [replLoading, setReplLoading] = useState(false);
  const [showRepl, setShowRepl] = useState(false);

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

        const assistantMsg: Message = {
          role: "assistant",
          content: r.text_answer || "Here are the results:",
          charts: r.charts || undefined,
          dataTable: r.data_table || undefined,
          sqlExecuted: r.sql_executed || undefined,
          codeExecuted: r.code_executed || undefined,
          suggestions: r.follow_up_suggestions,
        };

        setMessages((prev) => [...prev, assistantMsg]);

        // Add new charts to the main chart area
        if (r.charts && r.charts.length > 0) {
          const code = r.code_executed || r.sql_executed || undefined;
          setCharts((prev) => [
            ...prev,
            ...r.charts!.map((spec) => ({ spec, sourceCode: code })),
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
        <button
          onClick={() => setShowRepl(!showRepl)}
          style={styles.replToggle}
        >
          {showRepl ? "Hide REPL" : "Show REPL"}
        </button>
      </header>

      <div style={styles.body}>
        <div style={styles.leftSidebar}>
          <SessionHistory onReload={handleReload} loading={reloading} />
          <DatasetSidebar tables={tables} onAddDataset={handleAddDataset} />
        </div>

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

            {charts.length === 0 ? (
              <div style={styles.placeholder}>
                Charts will appear here as you explore the data.
              </div>
            ) : (
              <div style={styles.chartsGrid}>
                {charts.map((chart, i) => (
                  <PlotlyChart key={i} spec={chart.spec} sourceCode={chart.sourceCode} />
                ))}
              </div>
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
    gridTemplateColumns: "repeat(auto-fit, minmax(450px, 1fr))",
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
  chatArea: { width: 400, flexShrink: 0 },
};
