"""Health and readiness endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict:
    """Liveness probe endpoint."""
    return {
        "status": "ok",
        "time": datetime.now(timezone.utc).isoformat(),
    }
