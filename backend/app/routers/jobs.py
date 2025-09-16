"""Jobs router: upload PDFs, create job records, and enqueue processing tasks.

This router is now a thin HTTP layer that delegates to the orchestration
service for business logic. It still exposes the same endpoints and response
shapes as before.
"""
from __future__ import annotations

import io
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status, Request
from fastapi.responses import StreamingResponse
from ..services.orchestration.job_service import JobOrchestrationService

from ..config import get_settings
from ..deps import get_session_id
from ..models import JobItem, JobsCreateResponse, Limits, Invoice
from ..services.firestore import FirestoreService
from ..utils.network import get_client_ip

router = APIRouter(tags=["jobs"])
job_service = JobOrchestrationService()


"""Utilities `get_client_ip` and `count_pdf_pages` are imported from app.utils.* modules."""


@router.post(
    "/jobs",
    response_model=JobsCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    response_model_exclude_none=True,
)
async def create_jobs(
    files: List[UploadFile] = File(description="One or more PDF files to process"),
    session_id: str = Depends(get_session_id),
    request: Request = None,
) -> JobsCreateResponse:
    """Create processing jobs for uploaded PDFs via orchestration service."""
    settings = get_settings()
    client_ip = get_client_ip(request)
    job_items = await job_service.create_upload_jobs(session_id, files, client_ip=client_ip)
    return JobsCreateResponse(
        sessionId=session_id,
        jobs=job_items,
        limits=Limits(
            maxFiles=settings.MAX_FILES,
            maxSizeMb=settings.MAX_SIZE_MB,
            maxPages=settings.MAX_PAGES,
        ),
    )


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str, session_id: str = Depends(get_session_id)) -> dict:
    """Return current job status and result (if available). Requires session header."""
    store = FirestoreService()
    job = store.get_job(job_id)
    if not job or job.get("sessionId") != session_id:
        raise HTTPException(status_code=404, detail="Job not found")

    # Return selected fields
    return {
        "jobId": job.get("jobId"),
        "status": job.get("status"),
        "stages": job.get("stages", {}),
        "sizeBytes": job.get("sizeBytes"),
        "pageCount": job.get("pageCount"),
        "resultJson": job.get("resultJson"),
        "confidenceScore": job.get("confidenceScore"),
        "error": job.get("error"),
    }


@router.get("/sessions/{session_id}/jobs")
async def list_session_jobs(session_id: str, header_session: str = Depends(get_session_id)) -> dict:
    """List all jobs for a session. Path must match X-Session-Id header."""
    if session_id != header_session:
        raise HTTPException(status_code=400, detail="Session mismatch")
    store = FirestoreService()
    docs = store.list_jobs_by_session(session_id)
    # sort by createdAt desc if present
    jobs = [
        {
            "jobId": d.get("jobId"),
            "filename": d.get("filename"),
            "status": d.get("status"),
            "stages": d.get("stages", {}),
            "sizeBytes": d.get("sizeBytes"),
            "pageCount": d.get("pageCount"),
        }
        for d in docs
    ]
    return {"sessionId": session_id, "jobs": jobs}


@router.post("/jobs/{job_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_job(job_id: str, session_id: str = Depends(get_session_id), request: Request = None) -> dict:
    """Re-enqueue a job if its input PDF still exists; otherwise 409 re-upload required."""
    await job_service.retry_job(job_id, session_id)
    return {"jobId": job_id, "status": "queued"}


@router.get("/sessions/{session_id}/export.csv")
async def export_session_csv(session_id: str, header_session: str = Depends(get_session_id)):
    """Export all completed invoices for a session as CSV."""
    if session_id != header_session:
        raise HTTPException(status_code=400, detail="Session mismatch")
    csv_bytes = await job_service.get_session_jobs_as_csv(session_id)
    headers = {"Content-Disposition": f"attachment; filename=export-{session_id}.csv"}
    return StreamingResponse(io.BytesIO(csv_bytes), media_type="text/csv; charset=utf-8", headers=headers)


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, header_session: str = Depends(get_session_id)) -> dict:
    """Delete all jobs for a session and their input PDFs immediately."""
    if session_id != header_session:
        raise HTTPException(status_code=400, detail="Session mismatch")
    deleted = await job_service.delete_session_data(session_id)
    return {"sessionId": session_id, "deleted": deleted}
