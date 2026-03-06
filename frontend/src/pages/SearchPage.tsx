import { useState, useEffect, useRef, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { datasetApi, analysisApi, type DatasetResult } from "../api/client";
import DatasetCard from "../components/DatasetCard";
import UploadModal from "../components/UploadModal";
import { useAuth } from "../hooks/useAuth";

const SEARCH_STEPS = [
  "Searching data.gov...",
  "Searching World Bank...",
  "Searching Kaggle...",
  "Searching HuggingFace...",
  "Searching SDOH Place...",
  "Searching CMS Medicare/Medicaid...",
  "Searching Harvard Dataverse...",
  "Searching HUD Open Data...",
  "Searching BLS...",
  "Searching FRED...",
  "Searching CMAP Data Hub...",
  "Searching Census.gov...",
  "Ranking results by relevance...",
];

const SOURCES = [
  { name: "data.gov", color: "#0071bc" },
  { name: "World Bank", color: "#009fda" },
  { name: "Kaggle", color: "#20beff" },
  { name: "HuggingFace", color: "#ff9d00" },
  { name: "SDOH Place", color: "#4caf50" },
  { name: "CMS", color: "#d63384" },
  { name: "Harvard Dataverse", color: "#a51c30" },
  { name: "HUD", color: "#008542" },
  { name: "BLS", color: "#003366" },
  { name: "FRED", color: "#1a5276" },
  { name: "CMAP", color: "#6c3483" },
  { name: "Census", color: "#b7410e" },
];

const LOADING_STEPS = [
  "Downloading dataset...",
  "Loading into analysis engine...",
  "Profiling columns and values...",
  "Running data quality assessment...",
  "Generating preliminary charts...",
];

function useProgressSteps(active: boolean, steps: string[], intervalMs = 2200) {
  const [stepIndex, setStepIndex] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval>>(undefined);

  useEffect(() => {
    if (active) {
      setStepIndex(0);
      timerRef.current = setInterval(() => {
        setStepIndex((prev) => (prev < steps.length - 1 ? prev + 1 : prev));
      }, intervalMs);
    } else {
      clearInterval(timerRef.current);
      setStepIndex(0);
    }
    return () => clearInterval(timerRef.current);
  }, [active, steps, intervalMs]);

  return active ? steps[stepIndex] ?? "" : "";
}

export default function SearchPage() {
  const [question, setQuestion] = useState("");
  const [results, setResults] = useState<DatasetResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [starting, setStarting] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [showUpload, setShowUpload] = useState(false);
  const [error, setError] = useState("");
  const [searchDone, setSearchDone] = useState(false);
  const { logout } = useAuth();
  const navigate = useNavigate();

  const searchStatus = useProgressSteps(searching, SEARCH_STEPS);
  const loadingStatus = useProgressSteps(starting, LOADING_STEPS, 3000);
  const uploadStatus = useProgressSteps(uploading, LOADING_STEPS, 3000);

  const handleSearch = async (e: FormEvent) => {
    e.preventDefault();
    if (!question.trim()) return;
    setSearching(true);
    setError("");
    setResults([]);
    setSearchDone(false);
    try {
      const res = await datasetApi.search(question.trim());
      setResults(res.data);
      setSearchDone(true);
    } catch {
      setError("Search failed. Please try again.");
    } finally {
      setSearching(false);
    }
  };

  const handleSelect = async (dataset: DatasetResult) => {
    setStarting(true);
    setError("");
    try {
      const res = await analysisApi.start({
        source: dataset.source,
        dataset_id: dataset.id,
        question: question.trim(),
        download_url: dataset.download_url,
      });
      navigate(`/analysis/${res.data.session_id}`, {
        state: {
          question: question.trim(),
          startResponse: res.data,
          datasetTitle: dataset.title,
          datasetDescription:
            dataset.ai_description || dataset.description || "",
          downloadUrl: dataset.download_url,
        },
      });
    } catch {
      setError("Failed to load dataset. Please try another.");
    } finally {
      setStarting(false);
    }
  };

  const handleUpload = async (file: File, uploadQuestion: string) => {
    setUploading(true);
    setError("");
    try {
      const res = await analysisApi.upload(file, uploadQuestion);
      setShowUpload(false);
      navigate(`/analysis/${res.data.session_id}`, {
        state: {
          question: uploadQuestion || "Summarize and visualize this dataset",
          startResponse: res.data,
          datasetTitle: file.name,
          datasetDescription: `Uploaded file: ${file.name}`,
        },
      });
    } catch {
      setError("Failed to process uploaded file. Check the format and try again.");
    } finally {
      setUploading(false);
    }
  };

  const handleSampleSelect = async (url: string, name: string) => {
    setUploading(true);
    setError("");
    try {
      const res = await analysisApi.start({
        source: "upload",
        dataset_id: name,
        question: `Summarize and visualize this dataset: ${name}`,
        download_url: url,
      });
      setShowUpload(false);
      navigate(`/analysis/${res.data.session_id}`, {
        state: {
          question: `Summarize and visualize this dataset: ${name}`,
          startResponse: res.data,
          datasetTitle: name,
          datasetDescription: `Sample dataset: ${name}`,
          downloadUrl: url,
        },
      });
    } catch {
      setError("Failed to load sample dataset. Please try again.");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div style={styles.page}>
      <header style={styles.header}>
        <div style={styles.headerLeft}>
          <h1 style={styles.logo}>Public Data Analysis</h1>
          <button
            onClick={() => setShowUpload(true)}
            style={styles.uploadBtn}
          >
            Upload Data
          </button>
        </div>
        <button onClick={logout} style={styles.logoutBtn}>Log out</button>
      </header>

      <UploadModal
        open={showUpload}
        onClose={() => setShowUpload(false)}
        onUpload={handleUpload}
        onSampleSelect={handleSampleSelect}
        loading={uploading}
        loadingStatus={uploadStatus}
      />

      <main style={styles.main}>
        <h2 style={styles.heading}>
          What question do you want to explore with public data?
        </h2>
        <form onSubmit={handleSearch} style={styles.form}>
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="e.g. How have global CO2 emissions changed by country over the last 30 years?"
            rows={3}
            style={styles.textarea}
          />
          <button
            type="submit"
            disabled={searching || !question.trim()}
            style={styles.searchBtn}
          >
            {searching ? searchStatus : "Search Datasets"}
          </button>
        </form>
        <div style={styles.sourcesStrip}>
          <span style={styles.sourcesLabel}>Searches across</span>
          {SOURCES.map((s) => (
            <span
              key={s.name}
              style={{ ...styles.sourceChip, background: s.color }}
            >
              {s.name}
            </span>
          ))}
        </div>

        {error && <p style={styles.error}>{error}</p>}

        {starting && (
          <div style={styles.loading}>
            <div style={styles.spinner} />
            <span>{loadingStatus}</span>
          </div>
        )}

        {searchDone && results.length === 0 && !searching && (
          <div style={styles.noResults}>
            <p style={styles.noResultsText}>
              No downloadable datasets found for your query. Try rephrasing your question or using different keywords.
            </p>
          </div>
        )}

        {results.length > 0 && (
          <div style={styles.results}>
            <h3 style={styles.resultsHeading}>
              Found {results.length} relevant datasets
            </h3>
            <div style={styles.grid}>
              {results.map((d) => (
                <DatasetCard
                  key={`${d.source}-${d.id}`}
                  dataset={d}
                  onSelect={handleSelect}
                  disabled={starting}
                />
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  page: { minHeight: "100vh", background: "#f0f2f5" },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "1rem 2rem",
    background: "#fff",
    borderBottom: "1px solid #e5e7eb",
  },
  headerLeft: { display: "flex", alignItems: "center", gap: "1rem" },
  logo: { fontSize: "1.1rem", fontWeight: 700 },
  uploadBtn: {
    background: "#f0f2f5",
    border: "1px solid #d1d5db",
    borderRadius: "6px",
    padding: "0.35rem 0.75rem",
    cursor: "pointer",
    fontSize: "0.82rem",
    fontWeight: 600,
    color: "#374151",
  },
  logoutBtn: {
    background: "none",
    border: "1px solid #ddd",
    borderRadius: "6px",
    padding: "0.4rem 0.8rem",
    cursor: "pointer",
    fontSize: "0.85rem",
  },
  main: { maxWidth: 900, margin: "0 auto", padding: "2rem 1rem" },
  heading: { fontSize: "1.4rem", fontWeight: 600, marginBottom: "1rem" },
  form: { display: "flex", flexDirection: "column", gap: "0.75rem" },
  textarea: {
    padding: "0.8rem",
    border: "1px solid #ddd",
    borderRadius: "10px",
    fontSize: "1rem",
    resize: "vertical",
    fontFamily: "inherit",
  },
  searchBtn: {
    padding: "0.7rem",
    background: "#2563eb",
    color: "#fff",
    border: "none",
    borderRadius: "8px",
    fontSize: "1rem",
    fontWeight: 600,
    cursor: "pointer",
    alignSelf: "flex-start",
  },
  sourcesStrip: {
    display: "flex",
    flexWrap: "wrap",
    alignItems: "center",
    gap: "0.4rem",
    marginTop: "0.6rem",
  },
  sourcesLabel: {
    fontSize: "0.78rem",
    color: "#888",
    marginRight: "0.15rem",
  },
  sourceChip: {
    color: "#fff",
    padding: "1px 7px",
    borderRadius: "4px",
    fontSize: "0.7rem",
    fontWeight: 600,
    opacity: 0.85,
  },
  error: { color: "#dc2626", marginTop: "0.5rem" },
  loading: {
    marginTop: "2rem",
    padding: "1.2rem",
    background: "#fff",
    borderRadius: "10px",
    textAlign: "center",
    color: "#444",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: "0.75rem",
    fontSize: "0.95rem",
  },
  spinner: {
    width: 20,
    height: 20,
    border: "3px solid #e5e7eb",
    borderTop: "3px solid #2563eb",
    borderRadius: "50%",
    animation: "spin 0.8s linear infinite",
    flexShrink: 0,
  },
  noResults: {
    marginTop: "2rem",
    padding: "1.5rem",
    background: "#fff",
    borderRadius: "10px",
    textAlign: "center",
  },
  noResultsText: {
    color: "#6b7280",
    fontSize: "0.95rem",
    margin: 0,
  },
  results: { marginTop: "2rem" },
  resultsHeading: {
    fontSize: "1.1rem",
    fontWeight: 600,
    marginBottom: "1rem",
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
    gap: "1rem",
  },
};
