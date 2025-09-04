"""Jobs router: upload PDFs, create job records, and enqueue processing tasks."""
from __future__ import annotations

import asyncio
import io
import csv
import uuid
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pypdf import PdfReader
from google.cloud import firestore

from ..config import get_settings
from ..deps import get_session_id
from ..models import JobItem, JobsCreateResponse, Limits, Invoice
from ..services.firestore import FirestoreService
from ..services.gcs import GCSService
from ..services.tasks import CloudTasksService, TasksConfig
from .tasks import process_task as process_job_task

router = APIRouter(tags=["jobs"])


def _count_pdf_pages(data: bytes) -> int:
    try:
        reader = PdfReader(io.BytesIO(data))
        return len(reader.pages)
    except Exception as exc:  # noqa: BLE001 broad, returns user error
        raise HTTPException(status_code=400, detail="Invalid or unreadable PDF") from exc


@router.post(
    
    "/jobs",
    response_model=JobsCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    response_model_exclude_none=True,
)
async def create_jobs(
    files: List[UploadFile] = File(description="One or more PDF files to process"),
    session_id: str = Depends(get_session_id),
) -> JobsCreateResponse:
    """Create processing jobs for uploaded PDFs.

    Validates file count, MIME, size, and page count. Uploads each PDF to GCS,
    creates a Firestore job doc, and enqueues a Cloud Task for async processing.
    """
    settings = get_settings()

    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    if len(files) > settings.MAX_FILES:
        raise HTTPException(status_code=429, detail="Too many files in one request")

    gcs = GCSService(settings.GCS_BUCKET)
    store = FirestoreService()
    tasks = CloudTasksService(
        TasksConfig(
            project=settings.GCP_PROJECT,
            region=settings.REGION,
            queue=settings.TASKS_QUEUE,
            target_url=settings.TASKS_TARGET_URL,
            service_account_email=settings.TASKS_SERVICE_ACCOUNT_EMAIL,
            emulate=settings.TASKS_EMULATE,
        )
    )

    job_items: List[JobItem] = []

    for f in files:
        if f.content_type not in settings.ACCEPTED_MIME:
            raise HTTPException(status_code=400, detail=f"Unsupported MIME type: {f.content_type}")

        file_bytes = await f.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail=f"File {f.filename} is empty")

        size_bytes = len(file_bytes)
        if size_bytes > settings.MAX_SIZE_MB * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"File {f.filename} exceeds size limit")

        page_count = _count_pdf_pages(file_bytes)
        if page_count > settings.MAX_PAGES:
            raise HTTPException(status_code=400, detail=f"File {f.filename} exceeds page limit")

        job_id = str(uuid.uuid4())
        blob_path = f"uploads/{session_id}/{job_id}.pdf"
        gcs_uri = gcs.upload_bytes(blob_path, file_bytes, content_type="application/pdf")

        # Create Firestore job document
        store.create_job(
            job_id,
            {
                "jobId": job_id,
                "sessionId": session_id,
                "filename": f.filename,
                "sizeBytes": size_bytes,
                "pageCount": page_count,
                "gcsUri": gcs_uri,
                "status": "uploaded",
                "stages": {"uploaded": firestore.SERVER_TIMESTAMP},  # type: ignore[name-defined]
                "createdAt": firestore.SERVER_TIMESTAMP,  # type: ignore[name-defined]
                "updatedAt": firestore.SERVER_TIMESTAMP,  # type: ignore[name-defined]
            },
        )

        # Enqueue processing task (may be emulated locally)
        tasks.enqueue_job(job_id, session_id)
        store.set_job_status(job_id, "queued", "queued")

        # Local emulation: if TASKS_EMULATE is true, process asynchronously without Cloud Tasks
        if settings.TASKS_EMULATE:
            asyncio.create_task(
                process_job_task({"jobId": job_id, "sessionId": session_id})
            )

        job_items.append(
            JobItem(
                jobId=job_id,
                filename=f.filename,
                status="queued",
                sizeBytes=size_bytes,
                pageCount=page_count,
            )
        )

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
async def retry_job(job_id: str, session_id: str = Depends(get_session_id)) -> dict:
    """Re-enqueue a job if its input PDF still exists; otherwise 409 re-upload required."""
    settings = get_settings()
    store = FirestoreService()
    gcs = GCSService(settings.GCS_BUCKET)
    tasks = CloudTasksService(
        TasksConfig(
            project=settings.GCP_PROJECT,
            region=settings.REGION,
            queue=settings.TASKS_QUEUE,
            target_url=settings.TASKS_TARGET_URL,
            service_account_email=settings.TASKS_SERVICE_ACCOUNT_EMAIL,
            emulate=settings.TASKS_EMULATE,
        )
    )

    job = store.get_job(job_id)
    if not job or job.get("sessionId") != session_id:
        raise HTTPException(status_code=404, detail="Job not found")

    gcs_uri: str = job.get("gcsUri", "")
    prefix = f"gs://{settings.GCS_BUCKET}/"
    if gcs_uri.startswith(prefix):
        blob_path = gcs_uri[len(prefix) :]
        exists = gcs.blob_exists(blob_path)
    else:
        exists = False

    if not exists:
        raise HTTPException(status_code=409, detail="Original PDF not available; re-upload required")

    tasks.enqueue_job(job_id, session_id)
    store.set_job_status(job_id, "queued", "queued")
    # Local emulation: also trigger processing on retry
    if settings.TASKS_EMULATE:
        asyncio.create_task(
            process_job_task({"jobId": job_id, "sessionId": session_id})
        )
    return {"jobId": job_id, "status": "queued"}


@router.get("/sessions/{session_id}/export.csv")
async def export_session_csv(session_id: str, header_session: str = Depends(get_session_id)):
    """Export all completed invoices for a session as CSV."""
    if session_id != header_session:
        raise HTTPException(status_code=400, detail="Session mismatch")
    store = FirestoreService()
    docs = store.list_done_jobs_by_session(session_id)

    rows: List[dict] = []
    for d in docs:
        res = d.get("resultJson")
        if not res:
            continue
        try:
            inv = Invoice.model_validate_jsonish(res)
            rows.extend(
                inv.to_csv_rows(
                    filename=d.get("filename", ""),
                    confidence=d.get("confidenceScore"),
                )
            )
        except Exception:
            # skip invalid
            continue

    output = io.StringIO()
    fieldnames = [
        "invoiceNumber",
        "invoiceDate",
        "vendorName",
        "currency",
        "subtotal",
        "tax",
        "total",
        "dueDate",
        "lineItemIndex",
        "description",
        "quantity",
        "unitPrice",
        "lineTotal",
        "confidenceScore",
        "filename",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for r in rows:
        writer.writerow(r)

    csv_bytes = output.getvalue().encode("utf-8")
    headers = {"Content-Disposition": f"attachment; filename=export-{session_id}.csv"}
    return StreamingResponse(io.BytesIO(csv_bytes), media_type="text/csv; charset=utf-8", headers=headers)


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, header_session: str = Depends(get_session_id)) -> dict:
    """Delete all jobs for a session and their input PDFs immediately."""
    if session_id != header_session:
        raise HTTPException(status_code=400, detail="Session mismatch")
    settings = get_settings()
    store = FirestoreService()
    gcs = GCSService(settings.GCS_BUCKET)
    docs = store.list_jobs_by_session(session_id)
    deleted = 0
    for d in docs:
        gcs_uri: str = d.get("gcsUri", "")
        try:
            prefix = f"gs://{settings.GCS_BUCKET}/"
            if gcs_uri.startswith(prefix):
                blob_path = gcs_uri[len(prefix) :]
                gcs.delete_blob(blob_path)
        except Exception:
            pass
        try:
            store.delete_job(d.get("jobId"))
            deleted += 1
        except Exception:
            pass
    return {"sessionId": session_id, "deleted": deleted}
