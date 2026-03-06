from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
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
    _index_html = (frontend_dist / "index.html").read_text()

    # Serve static assets (JS, CSS, images) from the dist directory
    _assets_dir = frontend_dist / "assets"
    if _assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")

    # SPA fallback: serve index.html for all non-API routes so client-side
    # routing (React Router) works on refresh and direct navigation.
    @app.get("/{path:path}", include_in_schema=False)
    async def spa_fallback(request: Request) -> HTMLResponse | FileResponse:
        # Serve actual static files if they exist (e.g. favicon.svg)
        req_path = request.path_params["path"]
        if req_path and not req_path.startswith("api/"):
            file_path = (frontend_dist / req_path).resolve()
            if file_path.is_file() and str(file_path).startswith(str(frontend_dist)):
                return FileResponse(file_path)
        return HTMLResponse(_index_html)
