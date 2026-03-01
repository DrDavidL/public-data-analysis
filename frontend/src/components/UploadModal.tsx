import { useState, useRef, type DragEvent } from "react";

const SAMPLE_DATASETS = [
  {
    name: "Breast Cancer Clinical Data",
    file: "breastcancernew.csv",
    desc: "Diagnostic measurements for breast cancer classification",
  },
  {
    name: "Diabetes Prediction",
    file: "diabetes_prediction_dataset.csv",
    desc: "Health indicators for diabetes risk modeling",
  },
  {
    name: "Stroke Risk Factors",
    file: "healthcare-dataset-stroke-data.csv",
    desc: "Patient data with stroke outcome labels",
  },
  {
    name: "Clinical Trial (S1Data)",
    file: "S1Data.csv",
    desc: "Supplementary clinical research dataset",
  },
];

const SAMPLE_BASE_URL =
  "https://raw.githubusercontent.com/DrDavidL/autoanalyzer-ai/main/data/";

interface UploadModalProps {
  open: boolean;
  onClose: () => void;
  onUpload: (file: File, question: string) => void;
  onSampleSelect: (url: string, name: string) => void;
  loading: boolean;
  loadingStatus: string;
}

export default function UploadModal({
  open,
  onClose,
  onUpload,
  onSampleSelect,
  loading,
  loadingStatus,
}: UploadModalProps) {
  const [dragOver, setDragOver] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [question, setQuestion] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  if (!open) return null;

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) setSelectedFile(file);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) setSelectedFile(file);
  };

  const handleSubmit = () => {
    if (selectedFile) {
      onUpload(selectedFile, question);
    }
  };

  const handleClose = () => {
    if (!loading) {
      setSelectedFile(null);
      setQuestion("");
      onClose();
    }
  };

  return (
    <div style={styles.overlay} onClick={handleClose}>
      <div style={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div style={styles.modalHeader}>
          <h2 style={styles.modalTitle}>Upload Your Data</h2>
          <button
            onClick={handleClose}
            style={styles.closeBtn}
            disabled={loading}
          >
            x
          </button>
        </div>

        <div style={styles.warning}>
          <strong>No confidential data.</strong> Uploaded files are processed
          in-memory and discarded when your session ends, but this is a shared
          cloud service. Use only public or non-sensitive data.
        </div>

        {/* Drop zone */}
        <div
          style={{
            ...styles.dropZone,
            borderColor: dragOver ? "#2563eb" : "#d1d5db",
            background: dragOver ? "#eff6ff" : "#fafafa",
          }}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => fileRef.current?.click()}
        >
          <input
            ref={fileRef}
            type="file"
            accept=".csv,.xlsx,.xls,.json,.jsonl,.parquet"
            onChange={handleFileChange}
            style={{ display: "none" }}
          />
          {selectedFile ? (
            <div>
              <div style={styles.fileName}>{selectedFile.name}</div>
              <div style={styles.fileSize}>
                {(selectedFile.size / 1024).toFixed(0)} KB
              </div>
            </div>
          ) : (
            <div>
              <div style={styles.dropIcon}>+</div>
              <div style={styles.dropText}>
                Drop a file here or click to browse
              </div>
              <div style={styles.dropFormats}>
                CSV, Excel, JSON, Parquet (up to 100 MB)
              </div>
            </div>
          )}
        </div>

        {/* Question input */}
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="What would you like to explore? (optional)"
          style={styles.questionInput}
          disabled={loading}
        />

        <button
          onClick={handleSubmit}
          disabled={!selectedFile || loading}
          style={{
            ...styles.uploadBtn,
            opacity: !selectedFile || loading ? 0.6 : 1,
          }}
        >
          {loading ? loadingStatus || "Processing..." : "Analyze"}
        </button>

        {/* Sample datasets */}
        <div style={styles.sampleSection}>
          <div style={styles.sampleHeader}>
            Or try a sample public dataset
          </div>
          <div style={styles.sampleGrid}>
            {SAMPLE_DATASETS.map((ds) => (
              <button
                key={ds.file}
                style={styles.sampleCard}
                onClick={() =>
                  onSampleSelect(SAMPLE_BASE_URL + ds.file, ds.name)
                }
                disabled={loading}
              >
                <div style={styles.sampleName}>{ds.name}</div>
                <div style={styles.sampleDesc}>{ds.desc}</div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  overlay: {
    position: "fixed",
    inset: 0,
    background: "rgba(0,0,0,0.4)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 1000,
  },
  modal: {
    background: "#fff",
    borderRadius: "12px",
    padding: "1.5rem",
    width: "95%",
    maxWidth: "540px",
    maxHeight: "90vh",
    overflowY: "auto",
    boxShadow: "0 20px 60px rgba(0,0,0,0.15)",
  },
  modalHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: "0.75rem",
  },
  modalTitle: { fontSize: "1.15rem", fontWeight: 700, margin: 0 },
  closeBtn: {
    background: "none",
    border: "none",
    fontSize: "1.2rem",
    cursor: "pointer",
    color: "#888",
    padding: "0.25rem 0.5rem",
  },
  warning: {
    background: "#fef3c7",
    border: "1px solid #f59e0b",
    borderRadius: "8px",
    padding: "0.6rem 0.8rem",
    fontSize: "0.82rem",
    color: "#92400e",
    marginBottom: "1rem",
    lineHeight: 1.4,
  },
  dropZone: {
    border: "2px dashed #d1d5db",
    borderRadius: "10px",
    padding: "1.5rem",
    textAlign: "center",
    cursor: "pointer",
    transition: "border-color 0.15s, background 0.15s",
    marginBottom: "0.75rem",
  },
  dropIcon: {
    fontSize: "2rem",
    color: "#9ca3af",
    lineHeight: 1,
    marginBottom: "0.3rem",
  },
  dropText: { fontSize: "0.9rem", color: "#374151" },
  dropFormats: { fontSize: "0.75rem", color: "#9ca3af", marginTop: "0.25rem" },
  fileName: { fontSize: "0.95rem", fontWeight: 600, color: "#2563eb" },
  fileSize: { fontSize: "0.8rem", color: "#6b7280", marginTop: "0.15rem" },
  questionInput: {
    width: "100%",
    padding: "0.6rem 0.8rem",
    border: "1px solid #ddd",
    borderRadius: "8px",
    fontSize: "0.9rem",
    marginBottom: "0.75rem",
    boxSizing: "border-box",
    fontFamily: "inherit",
  },
  uploadBtn: {
    width: "100%",
    padding: "0.65rem",
    background: "#2563eb",
    color: "#fff",
    border: "none",
    borderRadius: "8px",
    fontSize: "0.95rem",
    fontWeight: 600,
    cursor: "pointer",
    marginBottom: "1rem",
  },
  sampleSection: {
    borderTop: "1px solid #e5e7eb",
    paddingTop: "0.75rem",
  },
  sampleHeader: {
    fontSize: "0.85rem",
    fontWeight: 600,
    color: "#6b7280",
    marginBottom: "0.5rem",
  },
  sampleGrid: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: "0.5rem",
  },
  sampleCard: {
    background: "#f8fafc",
    border: "1px solid #e5e7eb",
    borderRadius: "8px",
    padding: "0.5rem 0.6rem",
    textAlign: "left",
    cursor: "pointer",
    transition: "border-color 0.15s",
  },
  sampleName: { fontSize: "0.8rem", fontWeight: 600, color: "#1e293b" },
  sampleDesc: {
    fontSize: "0.72rem",
    color: "#64748b",
    marginTop: "0.15rem",
    lineHeight: 1.3,
  },
};
