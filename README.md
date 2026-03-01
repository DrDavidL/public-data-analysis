# Public Data Analysis Platform

AI-powered platform for searching, downloading, and analyzing public datasets with natural language Q&A and interactive visualizations.

## Features

- **Multi-source dataset search** — queries data.gov, World Bank, Kaggle, HuggingFace, and SDOH Place simultaneously
- **AI-ranked results** — GPT-5-mini ranks and describes datasets by relevance to your question
- **Interactive analysis** — ask follow-up questions in natural language, get SQL/Python-backed answers with Plotly charts
- **Secure REPL** — write your own SQL or Python against loaded datasets in a sandboxed environment
- **Cross-dataset joins** — load multiple datasets into the same DuckDB session and join them with SQL
- **Large dataset support** — DuckDB handles files larger than RAM via streaming

## Architecture

```
React (Vite + TypeScript + Plotly.js)
  ↓ /api/*
FastAPI
  ├── Auth (JWT + email allowlist)
  ├── Dataset Search (5 sources → GPT-5-mini ranking)
  ├── Analysis (GPT-5.2 → SQL/Plotly chart generation)
  ├── DuckDB (per-session, in-memory)
  └── Sandbox (RestrictedPython REPL)
```

## Prerequisites

- **Python 3.12+**
- **Node.js 22+**
- **[uv](https://docs.astral.sh/uv/)** — Python package manager
- **Azure OpenAI** — two deployments: a mini model (search/ranking) and a full model (analysis)

## Local Development

### 1. Clone and configure

```bash
git clone <repo-url>
cd public-data-analysis
cp .env.example .env
```

Edit `.env` with your credentials:

```env
# Azure OpenAI (required)
AZURE_API_VERSION="2024-12-01-preview"
AZURE_ENDPOINT="https://your-endpoint.openai.azure.com/"
AZURE_API_KEY="your-key"
AZURE_DEPLOYMENT_MINI="your-mini-deployment"
AZURE_DEPLOYMENT_FULL="your-full-deployment"

# Auth (required)
JWT_SECRET="generate-a-strong-secret"
ALLOWED_EMAILS="you@example.com"

# Dataset sources (optional, enables more results)
DATAGOV_API_KEY=""          # Free from api.data.gov
KAGGLE_API_TOKEN=""         # From kaggle.com/settings
```

### 2. Install dependencies

```bash
# Backend
cd backend && uv sync && cd ..

# Frontend
cd frontend && npm install && cd ..
```

### 3. Run

**Both servers at once:**

```bash
bash scripts/dev.sh
```

**Or separately:**

```bash
# Terminal 1 — backend on :8000
cd backend && uv run fastapi dev app/main.py --port 8000

# Terminal 2 — frontend on :5173
cd frontend && npm run dev
```

Open http://localhost:5173, register with an email from your `ALLOWED_EMAILS` list, and start searching.

### 4. Quality checks

```bash
# Lint (ruff check + format)
bash scripts/lint.sh

# Tests
cd backend && uv run pytest tests/ -v

# Dependency audit
bash scripts/audit.sh
```

## Docker

### Build

```bash
docker build -t public-data-analysis .
```

### Run locally

```bash
docker run --env-file .env -p 8000:8000 public-data-analysis
```

Open http://localhost:8000 — the container serves both the API and the built frontend.

## Deploy to Azure

### 1. Create Azure resources

```bash
# Variables
RG="public-data-analysis-rg"
ACR="publicdataanalysisacr"
APP="public-data-analysis-app"
PLAN="public-data-analysis-plan"
LOCATION="eastus"

# Resource group
az group create --name $RG --location $LOCATION

# Container registry
az acr create --resource-group $RG --name $ACR --sku Basic --admin-enabled true

# App Service plan (Linux, B1 or higher)
az appservice plan create \
  --name $PLAN \
  --resource-group $RG \
  --is-linux \
  --sku B1

# Web app (container-based)
az webapp create \
  --resource-group $RG \
  --plan $PLAN \
  --name $APP \
  --container-image-name "$ACR.azurecr.io/public-data-analysis:latest"
```

### 2. Push the Docker image

```bash
# Log in to ACR
az acr login --name $ACR

# Tag and push
docker tag public-data-analysis "$ACR.azurecr.io/public-data-analysis:latest"
docker push "$ACR.azurecr.io/public-data-analysis:latest"
```

### 3. Configure the web app

```bash
# Connect App Service to ACR
az webapp config container set \
  --name $APP \
  --resource-group $RG \
  --container-image-name "$ACR.azurecr.io/public-data-analysis:latest" \
  --container-registry-url "https://$ACR.azurecr.io"

# Set the port
az webapp config appsettings set \
  --name $APP \
  --resource-group $RG \
  --settings WEBSITES_PORT=8000

# Set environment variables (do NOT commit these)
az webapp config appsettings set \
  --name $APP \
  --resource-group $RG \
  --settings \
    AZURE_API_VERSION="2024-12-01-preview" \
    AZURE_ENDPOINT="https://your-endpoint.openai.azure.com/" \
    AZURE_API_KEY="your-key" \
    AZURE_MODEL_NAME_MINI="gpt-5-mini" \
    AZURE_DEPLOYMENT_MINI="your-mini-deployment" \
    AZURE_MODEL_NAME_FULL="gpt-5.2" \
    AZURE_DEPLOYMENT_FULL="your-full-deployment" \
    JWT_SECRET="your-production-secret" \
    ALLOWED_EMAILS="user1@example.com,user2@example.com" \
    DATAGOV_API_KEY="" \
    KAGGLE_API_TOKEN=""
```

### 4. Redeploy on updates

```bash
docker build -t "$ACR.azurecr.io/public-data-analysis:latest" .
docker push "$ACR.azurecr.io/public-data-analysis:latest"
az webapp restart --name $APP --resource-group $RG
```

### CI/CD

The included GitHub Actions workflow (`.github/workflows/ci.yml`) runs lint, audit, tests, frontend build, and Docker build on every push/PR to `main`. To add automatic deployment, extend it with an Azure login step and `az webapp restart`.

## Project Structure

```
public-data-analysis/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app
│   │   ├── config.py            # Settings from .env
│   │   ├── routers/             # auth, datasets, analysis
│   │   ├── services/            # AI, search, analysis, sandbox, datastore
│   │   │   └── sources/         # 5 dataset source adapters
│   │   ├── schemas/             # Pydantic models
│   │   └── core/                # JWT security, session manager
│   ├── tests/
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── pages/               # Login, Search, Analysis
│   │   ├── components/          # Charts, Chat, REPL, Sidebar
│   │   ├── hooks/               # useAuth
│   │   └── api/                 # Axios client
│   ├── package.json
│   └── vite.config.ts
├── scripts/                     # dev.sh, lint.sh, audit.sh
├── .github/workflows/ci.yml
├── Dockerfile
├── .env.example
└── CLAUDE.md
```
