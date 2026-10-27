from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import router as v1_router
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure local storage directory exists
    if settings.STORAGE_BACKEND == "local":
        from pathlib import Path
        Path(settings.LOCAL_STORAGE_PATH).mkdir(parents=True, exist_ok=True)
    from app.services.video_generation import recover
    import logging
    try:
        recover()
    except Exception:
        logging.getLogger(__name__).exception('Video recovery failed; check database connectivity')
    stop = None
    if settings.EXECUTION_AUTOMATION_ENABLED:
        from app.services.execution_automation import start
        stop = start()
    yield
    if stop:
        stop.set()
    from app.connectors.web_platform import shutdown_sessions
    shutdown_sessions()


app = FastAPI(
    title="营火AI · AI运营平台",
    version="0.1.0",
    description="Backend API for managing AI-powered business operations.",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(v1_router, prefix="/api/v1")


@app.get("/health", tags=["system"])
def health_check():
    return {"status": "ok", "environment": settings.ENVIRONMENT}


@app.get("/", tags=["system"])
def root():
    return {"message": "营火AI API", "docs": "/docs"}


# Serve local files with auth check
@app.get("/files/signed/{token}", tags=["files"])
def serve_signed_file(token: str):
    from app.core.security import verify_file_token
    from fastapi import HTTPException, status
    from fastapi.responses import FileResponse
    from pathlib import Path

    file_key = verify_file_token(token)
    if not file_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid or expired file token"
        )
    path = Path(settings.LOCAL_STORAGE_PATH) / file_key
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return FileResponse(path)
