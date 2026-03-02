from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers import admin, analysis, auth, datasets
from app.services import allowlist, user_store

app = FastAPI(title="Public Data Analysis", version="0.1.0")

# Seed runtime allowlist from config
allowlist.init(settings.allowed_emails)

# Initialize persistent user store
user_store.init(settings.azure_storage_connection_string)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router)
app.include_router(datasets.router)
app.include_router(analysis.router)
app.include_router(admin.router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# Serve frontend static files in production
frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="spa")
