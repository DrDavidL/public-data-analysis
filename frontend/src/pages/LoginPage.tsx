import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isRegister, setIsRegister] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { login, register } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (isRegister) {
        await register({ email, password });
      } else {
        await login({ email, password });
      }
      navigate("/search");
    } catch (err: unknown) {
      const resp = (err as { response?: { status?: number; data?: { detail?: string } } })?.response;
      const detail = resp?.data?.detail || "Authentication failed";
      if (resp?.status === 404 && !isRegister) {
        setError("No account found for this email. Click below to register.");
        setIsRegister(true);
      } else {
        setError(detail);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <h1 style={styles.title}>Public Data Analysis</h1>
        <p style={styles.subtitle}>
          Search, visualize, and analyze public datasets with AI
        </p>
        <form onSubmit={handleSubmit} style={styles.form}>
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            style={styles.input}
          />
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={6}
            style={styles.input}
          />
          {error && <p style={styles.error}>{error}</p>}
          <button type="submit" disabled={loading} style={styles.button}>
            {loading ? "..." : isRegister ? "Register" : "Log In"}
          </button>
        </form>
        <button
          onClick={() => setIsRegister(!isRegister)}
          style={styles.toggle}
        >
          {isRegister
            ? "Already have an account? Log in"
            : "Need an account? Register"}
        </button>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    minHeight: "100vh",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "#f0f2f5",
  },
  card: {
    background: "#fff",
    padding: "2.5rem",
    borderRadius: "12px",
    boxShadow: "0 2px 12px rgba(0,0,0,0.08)",
    width: "100%",
    maxWidth: "400px",
  },
  title: { fontSize: "1.5rem", fontWeight: 700, marginBottom: "0.25rem" },
  subtitle: { color: "#666", marginBottom: "1.5rem", fontSize: "0.9rem" },
  form: { display: "flex", flexDirection: "column", gap: "0.75rem" },
  input: {
    padding: "0.7rem 0.9rem",
    border: "1px solid #ddd",
    borderRadius: "8px",
    fontSize: "0.95rem",
  },
  button: {
    padding: "0.7rem",
    background: "#2563eb",
    color: "#fff",
    border: "none",
    borderRadius: "8px",
    fontSize: "0.95rem",
    fontWeight: 600,
    cursor: "pointer",
  },
  error: { color: "#dc2626", fontSize: "0.85rem" },
  toggle: {
    background: "none",
    border: "none",
    color: "#2563eb",
    cursor: "pointer",
    marginTop: "1rem",
    fontSize: "0.85rem",
  },
};
