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

// Redirect to login on 401
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
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
export interface StartResponse {
  session_id: string;
  table_name: string;
  columns: { name: string; type: string }[];
  row_count: number;
  summary_stats: Record<string, unknown>;
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

export const analysisApi = {
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
