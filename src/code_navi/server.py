"""Lightweight FastAPI gateway that assembles business-module routers."""

from __future__ import annotations

import os
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .learning.database import engine
from .learning.models import Base
from .learning.router import router as learning_router
from .provider_config import load_local_provider_config
from .research.router import router as research_router


def _cors_origins() -> list[str]:
    """Return configured browser origins, with loopback-only development defaults."""
    configured = os.getenv("CODE_NAVI_CORS_ORIGINS")
    if not configured:
        return ["http://127.0.0.1:3000", "http://localhost:3000"]
    return [origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()]

# ---------------------------------------------------------------------------
# Lifespan — ensure database tables exist on startup
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Create database directory and tables on startup."""
    load_local_provider_config()
    # Ensure parent directory exists for SQLite file-based storage
    from .learning.database import DATABASE_URL
    if DATABASE_URL.startswith("sqlite:///"):
        db_path = DATABASE_URL.replace("sqlite:///", "", 1)
        if db_path and not db_path.startswith("/"):
            db_path = os.path.abspath(db_path)
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Code Navi Backend API",
    description="Learning, teaching, and research assistance API",
    version="0.1.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Mount business-module routers
# ---------------------------------------------------------------------------
app.include_router(learning_router)
app.include_router(research_router)

# ---------------------------------------------------------------------------
# CORS — the browser secret configuration endpoint is restricted to the local UI.
# Register middleware AFTER mounting routers so it applies to all routes.
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# ---------------------------------------------------------------------------
# Global exception handler — ensures all error responses carry CORS headers
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch all unhandled exceptions and return JSON with details."""
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
    )


@app.get("/health", status_code=200)
async def health_check() -> dict[str, str]:
    """Basic liveness probe — returns 200 when the server is running."""
    return {"status": "ok"}
