"""GamePulse API - SYNTHETIC portfolio data, not affiliated with Garena or Free Fire."""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import CORS_ORIGINS, SYNTHETIC_NOTICE
from .routers import analytics, explorer, meta, operations
from .routers import importer as import_router
from .services import importer as import_service

app = FastAPI(
    title="GamePulse API",
    description=f"Gaming analytics & operations platform. {SYNTHETIC_NOTICE}",
    version="1.0.0",
)


@app.middleware("http")
async def pause_during_import(request: Request, call_next):
    """While data is being replaced the analysis tables are in flux: answer clearly instead of with errors."""
    path = request.url.path
    if path.startswith("/api/") and not path.startswith("/api/import") and path != "/api/health" and import_service.busy():
        return JSONResponse({"detail": "A data import is running. The data will be back in a moment."}, status_code=503)
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["*"],
)
app.include_router(meta.router)
app.include_router(analytics.router)
app.include_router(operations.router)
app.include_router(explorer.router)
app.include_router(import_router.router)
