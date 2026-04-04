# Public Data Analysis Platform

AI-powered platform for searching, downloading, and analyzing public datasets with natural language Q&A and interactive visualizations.

## Features

- **Multi-source dataset search** — queries 25 sources simultaneously with circuit breaker protection and disk-cached responses
- **AI-ranked results** — GPT-5-mini ranks and describes datasets by relevance to your question
- **Interactive analysis** — ask follow-up questions in natural language, get SQL/Python-backed answers with Plotly charts
- **Secure REPL** — write your own SQL or Python against loaded datasets in a sandboxed environment (pandas, numpy, plotly, scipy, datetime)
- **Cross-dataset joins** — load multiple datasets into the same DuckDB session and join them with SQL
- **Multi-format ingestion** — CSV, JSON, Parquet, Excel, PDF (table extraction), XML, GeoJSON, ZIP archives
- **Large dataset support** — DuckDB handles files larger than RAM via streaming
- **Admin tools** — manage allowed users at runtime, admin password reset, self-service password change

## Architecture

```
React (Vite + TypeScript + Plotly.js)
  ↓ /api/*
FastAPI
  ├── Auth (JWT + email allowlist)
  ├── Admin (runtime allowlist management)
  ├── Dataset Search (25 sources → GPT-5-mini ranking)
  ├── Analysis (GPT-5.2 → SQL/Plotly chart generation)
  ├── HTTP Client (circuit breaker + disk cache + retry)
  ├── DuckDB (per-session, in-memory)
  └── Sandbox (RestrictedPython REPL)
```

## Prerequisites

- **Python 3.12+**
- **Node.js 22+**
- **[uv](https://docs.astral.sh/uv/)** — Python package manager
- **LLM provider** — one of:
  - **Azure OpenAI** — two deployments: a mini model (search/ranking) and a full model (analysis)
  - **Ollama** — free, local, no API key needed
  - **OpenAI** — standard OpenAI API
 
## Screenshots

<img width="644" height="237" alt="image" src="https://github.com/user-attachments/assets/47022761-5de6-4064-b06c-3bb4c2b97c60" />

<img width="390" height="351" alt="image" src="https://github.com/user-attachments/assets/2a66283a-6d63-4be2-a4a9-7559d39eff2e" />

<img width="436" height="351" alt="image" src="https://github.com/user-attachments/assets/a3f2e3f3-6862-49df-8842-90e2f327c153" />

## Local Development (Azure OpenAI)

### 1. Clone and configure

```bash
git clone https://github.com/DrDavidL/public-data-analysis.git
cd public-data-analysis
cp .env.example .env
```

Edit `.env` with your credentials:

```env
LLM_PROVIDER="azure"

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
FRED_API_KEY=""             # Free from fred.stlouisfed.org
BLS_API_KEY=""              # Free from bls.gov/developers
EIA_API_KEY=""              # Free from eia.gov/opendata/register.php
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

## Running with Ollama (Free, Local LLM)

No cloud API or keys needed — run everything on your own machine using open-source models.

### 1. Install Ollama

Download from [ollama.com](https://ollama.com) or:

```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.com/install.sh | sh
```

### 2. Pull a model

```bash
# Good general-purpose model (~4.7 GB download)
ollama pull llama3.1

# For better analysis quality (requires ~40 GB RAM or a GPU with 48 GB VRAM)
ollama pull llama3.1:70b

# Strong at code generation — good balance of quality and size
ollama pull qwen2.5-coder:32b
```

### 3. Clone and configure

```bash
git clone https://github.com/DrDavidL/public-data-analysis.git
cd public-data-analysis
cp .env.example .env
```

Edit `.env`:

```env
LLM_PROVIDER="ollama"
OLLAMA_BASE_URL="http://localhost:11434/v1"
OLLAMA_MODEL_MINI="llama3.1"
OLLAMA_MODEL_FULL="llama3.1"

JWT_SECRET="any-local-secret"
ALLOWED_EMAILS=""              # empty = open access (anyone can register)
```

### 4. Install and run

```bash
# Install dependencies
cd backend && uv sync && cd ..
cd frontend && npm install && cd ..

# Start Ollama (if not already running)
ollama serve &

# Start the app
bash scripts/dev.sh
```

Open http://localhost:5173.

### Notes on local models

- **Quality varies** — Azure GPT-5.2 is significantly more capable at code generation and structured JSON output than most local models. Chart generation and complex analysis work best with 32B+ parameter models.
- **Recommended models** — `qwen2.5-coder:32b` is a good sweet spot for code/chart quality vs. hardware requirements. `llama3.1:70b` or `deepseek-r1:70b` for best results.
- **JSON output** — Smaller models may occasionally produce malformed JSON. The app has fallback parsing to handle this, but responses may sometimes fail.

## Office LAN Setup (Shared Server)

Run the LLM on one powerful machine and let office staff use the app from their browsers — no installs on their laptops.

### Option A: Single server runs everything (simplest)

```
[Server Machine — GPU + RAM]
├── Ollama (listening on 0.0.0.0:11434)
├── FastAPI backend (:8000)
└── Frontend (served by FastAPI via Docker)

[Staff laptops] → http://server-ip:8000
```

On the server:

```bash
# 1. Install Ollama and pull a model
ollama pull qwen2.5-coder:32b

# 2. Start Ollama on all interfaces so the app can reach it
OLLAMA_HOST=0.0.0.0 ollama serve &

# 3. Clone, configure, and run
git clone https://github.com/DrDavidL/public-data-analysis.git
cd public-data-analysis
cp .env.example .env
```

Edit `.env` on the server:

```env
LLM_PROVIDER="ollama"
OLLAMA_BASE_URL="http://localhost:11434/v1"
OLLAMA_MODEL_MINI="qwen2.5-coder:32b"
OLLAMA_MODEL_FULL="qwen2.5-coder:32b"

JWT_SECRET="generate-a-strong-secret"
ALLOWED_EMAILS="alice@office.com,bob@office.com"
CORS_ORIGINS="http://server-ip:8000"
```

```bash
# Build and run with Docker
docker build -t public-data-analysis .
docker run --env-file .env -p 8000:8000 public-data-analysis
```

Staff open `http://server-ip:8000` in their browser. No installs needed on their machines.

### Option B: Docker Compose (server + Ollama in one command)

Create a `docker-compose.yml`:

```yaml
services:
  ollama:
    image: ollama/ollama
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: [gpu]
    volumes:
      - ollama_data:/root/.ollama
    ports:
      - "11434:11434"

  app:
    build: .
    env_file: .env
    environment:
      OLLAMA_BASE_URL: "http://ollama:11434/v1"
    ports:
      - "8000:8000"
    depends_on:
      - ollama

volumes:
  ollama_data:
```

```bash
docker compose up -d
# Pull model into the Ollama container (one-time)
docker compose exec ollama ollama pull qwen2.5-coder:32b
```

### Hardware recommendations

| Model | Min RAM | GPU VRAM | Quality |
|-------|---------|----------|---------|
| `llama3.1` (8B) | 16 GB | 8 GB | Adequate for simple queries |
| `qwen2.5-coder:32b` | 32 GB | 24 GB | Strong at code/charts |
| `llama3.1:70b` (70B) | 64 GB | 48 GB | Good for complex analysis |
| `deepseek-r1:70b` | 64 GB | 48 GB | Best reasoning (closest to GPT-5) |

CPU-only inference works but is slow. A single NVIDIA GPU (RTX 4090, A6000, or better) is recommended for responsive performance.

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

Manage users and the email allowlist at runtime (requires `ADMIN_EMAILS` membership):

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

# Reset a user's password (admin only)
curl -X PUT -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "new_password": "new-secure-password"}' \
  https://your-app/api/admin/reset-password
```

Users can change their own password (requires authentication):

```bash
curl -X PUT -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"current_password": "old-password", "new_password": "new-password"}' \
  https://your-app/api/auth/change-password
```

Changes take effect immediately. The env var `ALLOWED_EMAILS` seeds the allowlist on startup; runtime changes persist until the app restarts.

## Data Sources

| Category | Sources |
|----------|---------|
| **Government** | data.gov, Census, BLS, FRED, EIA, HUD, CMAP, CMS |
| **Federal spending & regulation** | USASpending, Federal Register, SEC EDGAR, CFPB |
| **Health** | ClinicalTrials.gov, OpenFDA, Chicago Health Atlas, SDOH Place |
| **Environment** | EPA GHGRP |
| **Finance** | FDIC |
| **International** | World Bank, OECD, OWID, V-Dem |
| **Community** | Kaggle, HuggingFace, Harvard Dataverse |

## Project Structure

```
public-data-analysis/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app
│   │   ├── config.py            # Settings from .env
│   │   ├── routers/             # auth, datasets, analysis, admin
│   │   ├── services/            # AI, search, analysis, sandbox, datastore, http_client, allowlist
│   │   │   └── sources/         # 25 dataset source adapters
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
