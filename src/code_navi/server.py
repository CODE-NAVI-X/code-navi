"""Lightweight FastAPI gateway that assembles business-module routers."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .auth import models as auth_models  # noqa: F401  (register tables)
from .auth.router import router as auth_router
from .auth.settings import session_settings
from .classroom import models as classroom_models  # noqa: F401  (register tables)
from .classroom.router import router as classroom_router
from .context_transfer import models as context_transfer_models  # noqa: F401
from .context_transfer.router import router as context_transfer_router
from .db import DATABASE_URL, Base, engine
from .learning import models as learning_models  # noqa: F401  (register tables)
from .learning.router import router as learning_router
from .learning_profile import models as learning_profile_models  # noqa: F401  (register tables)
from .learning_profile.router import router as learning_profile_router
from .online_compiler import models as compiler_models  # noqa: F401  (register tables)
from .online_compiler.router import router as compiler_router
from .portraits.router import router as portraits_router
from .practice import models as practice_models  # noqa: F401  (register tables)
from .practice.router import router as practice_router
from .provider_config import load_local_provider_config
from .research import models as research_models  # noqa: F401  (register tables)
from .research.router import router as research_router
from .workspaces import models as workspace_models  # noqa: F401  (register tables)
from .workspaces.router import router as workspace_router

logger = logging.getLogger(__name__)

CORS_ORIGINS = session_settings.cors_origins

# ---------------------------------------------------------------------------
# Lifespan - ensure database tables exist on startup
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Create database directory and tables on startup."""
    load_local_provider_config()
    # Ensure parent directory exists for SQLite file-based storage
    if DATABASE_URL.startswith("sqlite:///"):
        db_path = DATABASE_URL.replace("sqlite:///", "", 1)
        if db_path and not db_path.startswith("/"):
            db_path = os.path.abspath(db_path)
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    yield


is_prod = session_settings.environment == "production"

app = FastAPI(
    title="Code Navi Backend API",
    description="Learning, teaching, and research assistance API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None if is_prod else "/docs",
    redoc_url=None if is_prod else "/redoc",
    openapi_url=None if is_prod else "/openapi.json",
)

# ---------------------------------------------------------------------------
# Mount business-module routers
# ---------------------------------------------------------------------------
app.include_router(auth_router)
app.include_router(learning_router)
app.include_router(learning_profile_router)
app.include_router(portraits_router)
app.include_router(research_router)
app.include_router(compiler_router)
app.include_router(practice_router)
app.include_router(context_transfer_router)
app.include_router(workspace_router)
app.include_router(classroom_router)

# ---------------------------------------------------------------------------
# CORS - explicit origin allowlist.
#
# A wildcard cannot be combined with credentials: browsers reject
# ``Access-Control-Allow-Origin: *`` on credentialed requests, so the previous
# wildcard silently broke exactly the requests it claimed to allow.  Set
# CODE_NAVI_CORS_ORIGINS to a comma-separated list to add deployment origins.
#
# Register middleware AFTER mounting routers so it applies to all routes.
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# ---------------------------------------------------------------------------
# Global exception handler - ensures all error responses carry CORS headers
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Return an opaque 500 and keep the diagnosis server-side.

    ``str(exc)`` leaks filesystem paths, SQL fragments and provider messages to
    the client, so only a correlation id crosses the boundary.
    """
    error_id = uuid4().hex
    logger.exception("Unhandled error %s on %s %s", error_id, request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error.", "error_id": error_id},
    )


@app.get("/health", status_code=200)
async def health_check() -> dict[str, str]:
    """Basic liveness probe - returns 200 when the server is running."""
    return {"status": "ok"}
