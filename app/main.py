"""FastAPI application entry point.

Run with:
    uv run uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.auth.routes import router as auth_router
from app.api.routes import router as api_router
from app.config import settings
from app.core.errors import register_error_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown events."""
    # Ensure token store directory exists (for SQLite fallback)
    import os
    os.makedirs(settings.token_store_path, exist_ok=True)

    # Initialize database (MariaDB or SQLite depending on config.toml)
    from app.db.database import get_db, close_db
    await get_db()

    yield

    # Cleanup
    await close_db()


app = FastAPI(
    title="Google Search Console Dashboard API",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS ───────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Error handlers ─────────────────────────────────────────────────────
register_error_handlers(app)

# ── Routers ───────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(api_router)


# ── Health check ───────────────────────────────────────────────────────
@app.get("/healthz", tags=["health"])
async def healthz():
    return {"status": "ok", "dry_run": settings.dry_run}


# ── SPA fallback (production: serve frontend static files) ─────────────
# Build the frontend (`cd frontend && npm run build`) and copy dist/ → app/static/
# The SPA is served for any non-API, non-auth route.
import os

static_dir = os.path.join(os.path.dirname(__file__), "static")

if os.path.isdir(static_dir):
    from fastapi.responses import FileResponse

    # Serve static assets (JS, CSS, images)
    assets_dir = os.path.join(static_dir, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        """Serve the SPA's index.html for any non-API route (client-side routing)."""
        # Don't intercept API or auth routes
        if full_path.startswith(("api/", "auth/", "healthz")):
            return {"error": "Not found"}
        # Check if a specific static file exists
        file_path = os.path.join(static_dir, full_path)
        if full_path and os.path.isfile(file_path):
            return FileResponse(file_path)
        # Fallback to index.html for SPA routing
        index_path = os.path.join(static_dir, "index.html")
        if os.path.isfile(index_path):
            return FileResponse(index_path)
        return {"error": "SPA not built. Run: cd frontend && npm run build"}
