import { useState, useEffect, useCallback } from "react";
import { useParams, useLocation, useNavigate } from "react-router-dom";
import { analysisApi, type AnalysisResponse, type TableInfo, type DataQualityReport as DQReport } from "../api/client";
import PlotlyChart from "../components/PlotlyChart";
import ChatPanel from "../components/ChatPanel";
import ReplPanel from "../components/ReplPanel";
import DatasetSidebar from "../components/DatasetSidebar";
import DataQualityReport from "../components/DataQualityReport";

interface Message {
  role: "user" | "assistant";
  content: string;
  charts?: Record<string, unknown>[];
  dataTable?: { data: Record<string, unknown>[]; columns: string[] };
  sqlExecuted?: string;
  codeExecuted?: string;
  suggestions?: string[];
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
  };
  datasetTitle: string;
  datasetDescription?: string;
}

export default function AnalysisPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const state = location.state as LocationState | null;

  const [charts, setCharts] = useState<Record<string, unknown>[]>(
    state?.startResponse.charts || [],
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
      setMessages([
        {
          role: "assistant",
          content: `Loaded "${state.datasetTitle}" (${state.startResponse.row_count.toLocaleString()} rows, ${state.startResponse.columns.length} columns).${chartsNote} Ask me anything about this data!${desc}`,
          suggestions: [
            "Summarize the key trends",
            "Show me the distribution of values",
            "What are the top 10 entries?",
          ],
        },
      ]);
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
          setCharts((prev) => [...prev, ...r.charts!]);
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
          setCharts((prev) => [...prev, ...figs]);
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
        <DatasetSidebar tables={tables} onAddDataset={handleAddDataset} />

        <div style={styles.mainArea}>
          {/* Charts area */}
          <div style={styles.chartsArea}>
            {/* Data Quality Report — shown above charts */}
            {state?.startResponse.data_quality &&
              state.startResponse.data_quality.columns?.length > 0 && (
                <DataQualityReport report={state.startResponse.data_quality} />
              )}

            {charts.length === 0 ? (
              <div style={styles.placeholder}>
                Charts will appear here as you explore the data.
              </div>
            ) : (
              <div style={styles.chartsGrid}>
                {charts.map((chart, i) => (
                  <PlotlyChart key={i} spec={chart} />
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
  chatArea: { width: 400, flexShrink: 0 },
};
