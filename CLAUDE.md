# Public Data Analysis Platform

AI-powered platform for searching, downloading, and analyzing public datasets with natural language Q&A and interactive visualizations.

## Architecture

```
React (Vite+TS+Plotly) → FastAPI → Azure OpenAI (GPT-5-mini search, GPT-5.2 analysis)
                                  → DuckDB (per-session, in-memory)
                                  → RestrictedPython sandbox (REPL)
                                  → 25 data sources
                                  → Shared HTTP client (circuit breaker + disk cache + retry)
```

## Key Files

| File | Purpose |
|------|---------|
| `backend/app/main.py` | FastAPI app entry |
| `backend/app/config.py` | Settings from .env |
| `backend/app/services/analysis.py` | AI Q&A + chart generation |
| `backend/app/services/sandbox.py` | RestrictedPython code execution |
| `backend/app/services/datastore.py` | DuckDB data operations + PDF/XML/GeoJSON/ZIP loading |
| `backend/app/services/http_client.py` | Shared HTTP client (circuit breaker, disk cache, retry) |
| `backend/app/services/sources/` | 25 data source adapters (one file each) |
| `backend/app/services/user_store.py` | Azure Table Storage user persistence |
| `backend/app/core/sessions.py` | Session manager (DuckDB + chat) |
| `frontend/src/pages/SearchPage.tsx` | Source selection + dataset search (SOURCES array) |
| `frontend/src/pages/AnalysisPage.tsx` | Main analysis workspace + dashboard view |
| `frontend/src/components/PlotlyChart.tsx` | Chart rendering + source labels (SOURCE_LABELS) |

## Commands

```bash
# Dev (both servers)
bash scripts/dev.sh

# Backend only
cd backend && uv run fastapi dev app/main.py --port 8000

# Frontend only
cd frontend && npm run dev

# Lint
bash scripts/lint.sh

# Test
cd backend && uv run pytest tests/ -v

# Audit
bash scripts/audit.sh
```

## Environment

Copy `.env.example` to `.env` and fill in Azure OpenAI credentials. See `.env.example` for all variables.

## Rules

- Both AI models are reasoning models: use `max_completion_tokens` (not `max_tokens`)
- Use `developer` role (not `system`) for Azure OpenAI messages
- DuckDB is per-session in-memory — no persistent database
- Sandbox blocks: `os`, `sys`, `subprocess`, `open`, `eval`, `exec`
- Sandbox pre-injects: `pd`, `np`, `px`, `go`, `datetime`, `scipy_stats`, `math`, `statistics`, `json`
- Datastore supports: CSV, TSV, JSON, JSONL, Parquet, Excel, PDF, XML, GeoJSON, ZIP
- HTTP client uses JSON-only disk cache (not pickle) to mitigate CVE-2025-69872
- SSRF protection: domain allowlist + DNS rebinding guard + redirect validation
- `_download_file` validates every redirect hop against the allowlist
- `.tsv`/`.tab` files: DuckDB gets explicit `delim='\t'` hint (auto-detect fails on some Harvard Dataverse files)
- Chart titles rendered as HTML divs above Plotly (not inside SVG) for word-wrap support
- Dashboard auto-exits when last chart is unpinned

## Auth Endpoints

- `POST /api/auth/register` — create account (email must be in allowlist)
- `POST /api/auth/login` — get JWT token
- `PUT /api/auth/change-password` — self-service (requires current password)
- `PUT /api/admin/reset-password` — admin resets any user's password
- User store: Azure Table Storage in production, in-memory for local dev

## Adding a New Data Source

1. Create `backend/app/services/sources/<name>.py` implementing `search()`, `get_download_url()`, `download()`
2. Register in `backend/app/services/dataset_search.py` (imports + `ALL_SOURCES` list)
3. Register in `backend/app/services/analysis.py` (both `source_adapters` dicts — there are 2 copies)
4. Add domain to `ALLOWED_DOWNLOAD_DOMAINS` in `analysis.py`
5. Add entry to `SOURCES` array in `frontend/src/pages/SearchPage.tsx`
6. Add label to `SOURCE_LABELS` in `frontend/src/components/PlotlyChart.tsx`

## Stress Testing

```bash
cd backend && uv run python -m tests.test_search_stress
```

10 diverse queries across all 25 sources. Results written to `tests/stress_test_results.json` (gitignored).
