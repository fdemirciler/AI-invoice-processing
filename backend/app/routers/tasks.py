"""Tasks worker endpoint (thin HTTP layer).

Delegates the full pipeline orchestration to `TaskPipelineService`:
Acquire lock -> OCR -> sanitize -> LLM -> validate -> score -> persist -> cleanup.
"""
from __future__ import annotations

from typing import Any, Dict
import logging

from fastapi import APIRouter, Depends, HTTPException

from ..deps import verify_oidc_token
from ..services.orchestration.task_pipeline import TaskPipelineService

router = APIRouter(prefix="/tasks", tags=["tasks"])  # mounted under /api
logger = logging.getLogger(__name__)


@router.post("/process")
async def process_task(
    payload: Dict[str, Any],
    decoded_token: dict = Depends(verify_oidc_token),
) -> Dict[str, Any]:
    """Process a job: expects JSON { jobId, sessionId }.

    In production with Cloud Tasks, this endpoint should verify the OIDC audience.
    For local development (TASKS_EMULATE=true), calls can be made directly without auth.
    """
    job_id = (payload or {}).get("jobId")
    session_id = (payload or {}).get("sessionId")
    if not job_id or not session_id:
        raise HTTPException(status_code=400, detail="Missing jobId or sessionId")

    pipeline = TaskPipelineService()
    return await pipeline.process_invoice_job(job_id, session_id)
