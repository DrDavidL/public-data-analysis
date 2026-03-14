import { useState, useEffect, useCallback } from "react";
import { sessionsApi, type SavedSession } from "../api/client";

interface Props {
  onReload: (sessionId: string) => void;
  loading: boolean;
}

export default function SessionHistory({ onReload, loading }: Props) {
  const [sessions, setSessions] = useState<SavedSession[]>([]);
  const [collapsed, setCollapsed] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  const fetchSessions = useCallback(() => {
    sessionsApi.history().then((res) => setSessions(res.data)).catch(() => {});
  }, []);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  const handleDelete = async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    if (!confirm("Delete this saved session?")) return;
    setDeleting(sessionId);
    try {
      await sessionsApi.delete(sessionId);
      setSessions((prev) => prev.filter((s) => s.session_id !== sessionId));
    } catch {
      // ignore
    } finally {
      setDeleting(null);
    }
  };

  const formatDate = (iso: string) => {
    if (!iso) return "";
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  };

  if (sessions.length === 0) return null;

  return (
    <div style={styles.container}>
      <button
        onClick={() => setCollapsed(!collapsed)}
        style={styles.header}
      >
        <span style={styles.headerText}>
          History ({sessions.length})
        </span>
        <span>{collapsed ? "+" : "\u2013"}</span>
      </button>
      {!collapsed && (
        <div style={styles.list}>
          {sessions.map((s) => (
            <div
              key={s.session_id}
              onClick={() => !loading && onReload(s.session_id)}
              style={{
                ...styles.item,
                opacity: loading ? 0.6 : 1,
                cursor: loading ? "wait" : "pointer",
              }}
            >
              <div style={styles.itemTitle}>
                {s.dataset_title || s.dataset_id || "Untitled"}
              </div>
              <div style={styles.itemQuestion}>
                {s.original_question?.slice(0, 80)}
                {(s.original_question?.length || 0) > 80 ? "..." : ""}
              </div>
              <div style={styles.itemMeta}>
                <span>{formatDate(s.updated_at || s.created_at)}</span>
                <button
                  onClick={(e) => handleDelete(e, s.session_id)}
                  disabled={deleting === s.session_id}
                  style={styles.deleteBtn}
                  title="Delete"
                >
                  {deleting === s.session_id ? "..." : "\u00d7"}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    borderBottom: "1px solid #e5e7eb",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    width: "100%",
    padding: "0.6rem 0.75rem",
    background: "#f8fafc",
    border: "none",
    borderBottom: "1px solid #e5e7eb",
    cursor: "pointer",
    fontSize: "0.8rem",
    fontWeight: 600,
    color: "#374151",
  },
  headerText: {
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  list: {
    maxHeight: "300px",
    overflowY: "auto",
  },
  item: {
    padding: "0.5rem 0.75rem",
    borderBottom: "1px solid #f3f4f6",
  },
  itemTitle: {
    fontSize: "0.78rem",
    fontWeight: 600,
    color: "#111827",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  itemQuestion: {
    fontSize: "0.72rem",
    color: "#6b7280",
    marginTop: "2px",
    lineHeight: 1.3,
  },
  itemMeta: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginTop: "3px",
    fontSize: "0.68rem",
    color: "#9ca3af",
  },
  deleteBtn: {
    background: "none",
    border: "none",
    color: "#9ca3af",
    cursor: "pointer",
    fontSize: "0.9rem",
    padding: "0 2px",
    lineHeight: 1,
  },
};
