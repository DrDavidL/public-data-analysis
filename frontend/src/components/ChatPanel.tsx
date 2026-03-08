import { useState, type FormEvent } from "react";
import type { AnalysisResponse } from "../api/client";

interface Message {
  role: "user" | "assistant";
  content: string;
  sqlExecuted?: string;
  codeExecuted?: string;
  suggestions?: string[];
}

interface Props {
  messages: Message[];
  onAsk: (question: string) => Promise<AnalysisResponse>;
  loading: boolean;
}

export default function ChatPanel({ messages, onAsk, loading }: Props) {
  const [input, setInput] = useState("");

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;
    const q = input.trim();
    setInput("");
    onAsk(q);
  };

  const handleSuggestion = (s: string) => {
    if (loading) return;
    onAsk(s);
  };

  return (
    <div style={styles.container}>
      <div style={styles.messages}>
        {messages.map((msg, i) => (
          <div
            key={i}
            style={{
              ...styles.message,
              alignSelf: msg.role === "user" ? "flex-end" : "flex-start",
              background: msg.role === "user" ? "#2563eb" : "#f3f4f6",
              color: msg.role === "user" ? "#fff" : "#111",
            }}
          >
            <p style={{ whiteSpace: "pre-wrap" }}>{msg.content}</p>
            {msg.sqlExecuted && (
              <details style={styles.codeDetails}>
                <summary>SQL Query</summary>
                <pre style={styles.code}>{msg.sqlExecuted}</pre>
              </details>
            )}
            {msg.codeExecuted && (
              <details style={styles.codeDetails}>
                <summary>Python Code</summary>
                <pre style={styles.code}>{msg.codeExecuted}</pre>
              </details>
            )}
            {msg.suggestions && msg.suggestions.length > 0 && (
              <div style={styles.suggestions}>
                {msg.suggestions.map((s, si) => (
                  <button
                    key={si}
                    onClick={() => handleSuggestion(s)}
                    style={styles.chip}
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div style={{ ...styles.message, background: "#f3f4f6" }}>
            Analyzing...
          </div>
        )}
      </div>
      <form onSubmit={handleSubmit} style={styles.form}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question about the data..."
          style={styles.input}
          disabled={loading}
        />
        <button type="submit" disabled={loading} style={styles.sendBtn}>
          Send
        </button>
      </form>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: "flex",
    flexDirection: "column",
    height: "100%",
    borderLeft: "1px solid #e5e7eb",
  },
  messages: {
    flex: 1,
    overflowY: "auto",
    padding: "1rem",
    display: "flex",
    flexDirection: "column",
    gap: "0.75rem",
  },
  message: {
    maxWidth: "90%",
    padding: "0.75rem 1rem",
    borderRadius: "10px",
    fontSize: "0.9rem",
    lineHeight: 1.5,
  },
  codeDetails: { marginTop: "0.5rem", fontSize: "0.8rem" },
  code: {
    background: "#1e293b",
    color: "#e2e8f0",
    padding: "0.5rem",
    borderRadius: "6px",
    overflow: "auto",
    fontSize: "0.8rem",
    marginTop: "0.25rem",
  },
  suggestions: {
    display: "flex",
    flexWrap: "wrap",
    gap: "0.5rem",
    marginTop: "0.5rem",
  },
  chip: {
    padding: "4px 10px",
    background: "#e0e7ff",
    border: "none",
    borderRadius: "16px",
    fontSize: "0.8rem",
    cursor: "pointer",
    color: "#3730a3",
  },
  form: {
    display: "flex",
    gap: "0.5rem",
    padding: "0.75rem 1rem",
    borderTop: "1px solid #e5e7eb",
  },
  input: {
    flex: 1,
    padding: "0.6rem 0.8rem",
    border: "1px solid #ddd",
    borderRadius: "8px",
    fontSize: "0.9rem",
  },
  sendBtn: {
    padding: "0.6rem 1rem",
    background: "#2563eb",
    color: "#fff",
    border: "none",
    borderRadius: "8px",
    fontWeight: 600,
    cursor: "pointer",
  },
};
