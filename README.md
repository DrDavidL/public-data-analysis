# Public Data Analysis Platform

AI-powered platform for searching, downloading, and analyzing public datasets with natural language Q&A and interactive visualizations.

## Features

- **Multi-source dataset search** — queries 7 sources (data.gov, World Bank, Kaggle, HuggingFace, SDOH Place, CMS, Harvard Dataverse) simultaneously
- **AI-ranked results** — GPT-5-mini ranks and describes datasets by relevance to your question
- **Interactive analysis** — ask follow-up questions in natural language, get SQL/Python-backed answers with Plotly charts
- **Secure REPL** — write your own SQL or Python against loaded datasets in a sandboxed environment
- **Cross-dataset joins** — load multiple datasets into the same DuckDB session and join them with SQL
- **Large dataset support** — DuckDB handles files larger than RAM via streaming
- **Admin email management** — add/remove allowed users at runtime without restarting

## Architecture

```
React (Vite + TypeScript + Plotly.js)
  ↓ /api/*
FastAPI
  ├── Auth (JWT + email allowlist)
  ├── Admin (runtime allowlist management)
  ├── Dataset Search (7 sources → GPT-5-mini ranking)
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
git clone https://github.com/DrDavidL/public-data-analysis.git
cd public-data-analysis
cp .env.example .env
```

Edit `.env` with your credentials:

```env
# Azure OpenAI (required)
AZURE_ENDPOINT="https://your-endpoint.openai.azure.com/"
AZURE_API_KEY="your-key"
AZURE_DEPLOYMENT_MINI="your-mini-deployment"
AZURE_DEPLOYMENT_FULL="your-full-deployment"

# Auth (required)
JWT_SECRET="generate-a-strong-secret"
ALLOWED_EMAILS="you@example.com"
ADMIN_EMAILS="you@example.com"

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

## Deploy to Azure Container Apps

The app runs on Azure Container Apps with automatic CI/CD via GitHub Actions.

### 1. Create Azure resources

```bash
RG="pubdata-rg"
ACR="pubdataacr"
ENV="pubdata-env"
APP="pubdata-app"
LOCATION="eastus"

# Resource group
az group create --name $RG --location $LOCATION

# Container registry
az acr create --resource-group $RG --name $ACR --sku Basic --admin-enabled true

# Container Apps environment
az containerapp env create --name $ENV --resource-group $RG --location $LOCATION
```

### 2. Build and push the Docker image

```bash
az acr login --name $ACR
docker build --platform linux/amd64 -t $ACR.azurecr.io/public-data-analysis:latest .
docker push $ACR.azurecr.io/public-data-analysis:latest
```

### 3. Create the Container App

```bash
az containerapp create \
  --name $APP \
  --resource-group $RG \
  --environment $ENV \
  --image $ACR.azurecr.io/public-data-analysis:latest \
  --registry-server $ACR.azurecr.io \
  --target-port 8000 \
  --ingress external \
  --min-replicas 0 \
  --max-replicas 3 \
  --cpu 1 \
  --memory 2Gi \
  --env-vars \
    AZURE_ENDPOINT="https://your-endpoint.openai.azure.com/" \
    AZURE_API_KEY="your-key" \
    AZURE_DEPLOYMENT_MINI="your-mini-deployment" \
    AZURE_DEPLOYMENT_FULL="your-full-deployment" \
    JWT_SECRET="your-production-secret" \
    ALLOWED_EMAILS="you@example.com" \
    ADMIN_EMAILS="you@example.com" \
    CORS_ORIGINS="https://your-app.azurecontainerapps.io"
```

### 4. CI/CD with GitHub Actions

The workflow (`.github/workflows/ci.yml`) runs lint, tests, frontend build, and Docker build on every push/PR. On push to `main`, it also deploys to Azure Container Apps.

**Required GitHub secrets:**

| Secret | Value |
|--------|-------|
| `AZURE_CREDENTIALS` | Service principal JSON from `az ad sp create-for-rbac --sdk-auth` |
| `ACR_USERNAME` | ACR admin username |
| `ACR_PASSWORD` | ACR admin password |

**Required GitHub variables:**

| Variable | Value |
|----------|-------|
| `ACR_LOGIN_SERVER` | e.g. `pubdataacr.azurecr.io` |
| `CONTAINER_APP_NAME` | e.g. `pubdata-app` |
| `RESOURCE_GROUP` | e.g. `pubdata-rg` |

### 5. Manual redeploy

```bash
az acr login --name $ACR
docker build --platform linux/amd64 -t $ACR.azurecr.io/public-data-analysis:latest .
docker push $ACR.azurecr.io/public-data-analysis:latest
az containerapp update --name $APP --resource-group $RG \
  --image $ACR.azurecr.io/public-data-analysis:latest
```

## Admin API

Manage the email allowlist at runtime (requires `ADMIN_EMAILS` membership):

```bash
TOKEN="your-jwt-token"

# List allowed emails
curl -H "Authorization: Bearer $TOKEN" https://your-app/api/admin/allowlist

# Add emails
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"emails": ["new@example.com"]}' \
  https://your-app/api/admin/allowlist

# Remove an email
curl -X DELETE -H "Authorization: Bearer $TOKEN" \
  https://your-app/api/admin/allowlist/old@example.com
```

Changes take effect immediately. The env var `ALLOWED_EMAILS` seeds the allowlist on startup; runtime changes persist until the app restarts.

## Project Structure

```
public-data-analysis/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app
│   │   ├── config.py            # Settings from .env
│   │   ├── routers/             # auth, datasets, analysis, admin
│   │   ├── services/            # AI, search, analysis, sandbox, datastore, allowlist
│   │   │   └── sources/         # 7 dataset source adapters
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
├── .dockerignore
├── .env.example
└── CLAUDE.md
```
