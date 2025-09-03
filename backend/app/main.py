"""
Main FastAPI application for the Invoice Processing backend.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import logging
from contextlib import asynccontextmanager

from .config import get_settings
from .routers.health import router as health_router
from .routers.config import router as config_router
from .routers.jobs import router as jobs_router
from .routers.tasks import router as tasks_router


settings = get_settings()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    if settings.RETENTION_LOOP_ENABLE:
        app.state._retention_task = asyncio.create_task(_retention_loop())
    try:
        yield
    finally:
        # Shutdown
        t = getattr(app.state, "_retention_task", None)
        if t and not t.done():
            t.cancel()


app = FastAPI(
    title="Invoice Processing API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health_router, prefix=settings.API_PREFIX)
app.include_router(config_router, prefix=settings.API_PREFIX)
app.include_router(jobs_router, prefix=settings.API_PREFIX)
app.include_router(tasks_router, prefix=settings.API_PREFIX)


@app.get("/", tags=["root"])
async def root() -> dict:
    """Simple root endpoint."""
    return {"name": app.title, "version": app.version}


async def _retention_loop() -> None:
    from .services.firestore import FirestoreService

    while True:
        try:
            deleted = FirestoreService().delete_stale_jobs(settings.RETENTION_HOURS)
            if deleted:
                logger.info("Retention: deleted %d stale jobs", deleted)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Retention loop error: %s", exc)
        await asyncio.sleep(settings.RETENTION_LOOP_INTERVAL_MIN * 60)


