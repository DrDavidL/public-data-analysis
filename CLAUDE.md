# Public Data Analysis Platform

AI-powered platform for searching, downloading, and analyzing public datasets with natural language Q&A and interactive visualizations.

## Architecture

```
React (Vite+TS+Plotly) → FastAPI → Azure OpenAI (GPT-5-mini search, GPT-5.2 analysis)
                                  → DuckDB (per-session, in-memory)
                                  → RestrictedPython sandbox (REPL)
                                  → 12 data sources (data.gov, World Bank, Kaggle, HuggingFace, SDOH Place, CMS, Harvard Dataverse, HUD, BLS, FRED, CMAP, Census)
```

## Key Files

| File | Purpose |
|------|---------|
| `backend/app/main.py` | FastAPI app entry |
| `backend/app/config.py` | Settings from .env |
| `backend/app/services/analysis.py` | AI Q&A + chart generation |
| `backend/app/services/sandbox.py` | RestrictedPython code execution |
| `backend/app/services/datastore.py` | DuckDB data operations |
| `backend/app/core/sessions.py` | Session manager (DuckDB + chat) |
| `frontend/src/pages/AnalysisPage.tsx` | Main analysis workspace |

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
