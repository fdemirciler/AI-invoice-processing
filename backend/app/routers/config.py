"""Runtime config endpoint for frontend consumption."""
from __future__ import annotations

from fastapi import APIRouter

from ..config import get_settings

router = APIRouter(tags=["config"])


@router.get("/config")
async def get_config() -> dict:
    """Expose non-sensitive runtime limits and accepted MIME types."""
    settings = get_settings()
    return {
        "maxFiles": settings.MAX_FILES,
        "maxSizeMb": settings.MAX_SIZE_MB,
        "maxPages": settings.MAX_PAGES,
        "acceptedMime": settings.ACCEPTED_MIME,
    }
