import axios from "axios";

const api = axios.create({ baseURL: "/api" });

// Attach JWT token to every request
api.interceptors.request.use((config) => {
  const token = sessionStorage.getItem("token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Redirect to login on 401 (skip for auth endpoints so login errors are visible)
api.interceptors.response.use(
  (res) => res,
  (err) => {
    const url = err.config?.url || "";
    const isAuthEndpoint = url.startsWith("/auth/");
    if (err.response?.status === 401 && !isAuthEndpoint) {
      sessionStorage.removeItem("token");
      window.location.href = "/login";
    }
    return Promise.reject(err);
  },
);

export interface LoginRequest {
  email: string;
  password: string;
}
export interface TokenResponse {
  access_token: string;
  token_type: string;
}
export interface DatasetResult {
  source: string;
  id: string;
  title: string;
  description: string;
  formats: string[];
  size_bytes: number | null;
  download_url: string | null;
  metadata: Record<string, unknown>;
  ai_description: string | null;
}
export interface StartRequest {
  source: string;
  dataset_id: string;
  question: string;
  download_url: string | null;
}
export interface DataQualityFinding {
  severity: "error" | "warning" | "info";
  message: string;
}
export interface DataQualityColumnReport {
  name: string;
  type: string;
  missing_count?: number;
  missing_pct?: number;
  distinct_count?: number;
  outlier_count?: number;
  outlier_pct?: number;
  issues: string[];
}
export interface DataQualityReport {
  row_count: number;
  column_count: number;
  duplicate_rows: number;
  completeness_pct: number;
  overall_score: number;
  summary: string;
  columns: DataQualityColumnReport[];
  findings: DataQualityFinding[];
}
export interface StartResponse {
  session_id: string;
  table_name: string;
  columns: { name: string; type: string }[];
  row_count: number;
  summary_stats: Record<string, unknown>;
  data_quality: DataQualityReport;
  charts: Record<string, unknown>[];
}
export interface AskRequest {
  session_id: string;
  question: string;
}
export interface AnalysisResponse {
  text_answer: string | null;
  charts: Record<string, unknown>[] | null;
  data_table: { data: Record<string, unknown>[]; columns: string[] } | null;
  code_executed: string | null;
  sql_executed: string | null;
  follow_up_suggestions: string[];
}
export interface TableInfo {
  name: string;
  columns: { name: string; type: string }[];
  row_count: number;
}

export const authApi = {
  login: (data: LoginRequest) =>
    api.post<TokenResponse>("/auth/login", data),
  register: (data: LoginRequest) =>
    api.post<TokenResponse>("/auth/register", data),
  me: () => api.get<{ email: string }>("/auth/me"),
};

export const datasetApi = {
  search: (question: string) =>
    api.post<DatasetResult[]>("/datasets/search", { question }),
};

export interface UploadResponse {
  session_id: string;
  table_name: string;
  columns: { name: string; type: string }[];
  row_count: number;
  summary_stats: Record<string, unknown>;
  data_quality: DataQualityReport;
  charts: Record<string, unknown>[];
}

export const analysisApi = {
  upload: (file: File, question?: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("question", question || "Summarize and visualize this dataset");
    return api.post<UploadResponse>("/analysis/upload", form);
  },
  start: (data: StartRequest) =>
    api.post<StartResponse>("/analysis/start", data),
  ask: (data: AskRequest) =>
    api.post<AnalysisResponse>("/analysis/ask", data),
  addDataset: (data: { session_id: string; source: string; dataset_id: string; download_url: string | null }) =>
    api.post<StartResponse>("/analysis/add-dataset", data),
  tables: (sessionId: string) =>
    api.get<{ tables: TableInfo[] }>(`/analysis/tables/${sessionId}`),
  execute: (sessionId: string, code: string, language: string) =>
    api.post<Record<string, unknown>>(`/analysis/execute/${sessionId}`, { code, language }),
};

export default api;
