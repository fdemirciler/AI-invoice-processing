from __future__ import annotations

import asyncio
import io
import csv
import uuid
from typing import List
import logging

from fastapi import UploadFile, HTTPException
from google.cloud import firestore

from ...config import get_settings
from ...models import JobItem, Invoice
from ...services.firestore import FirestoreService
from ...services.gcs import GCSService
from ...services.rate_limit import RateLimiterService
from ...services.tasks import CloudTasksService, TasksConfig
from ...utils.pdf import count_pdf_pages
from ...exceptions import (
    FileValidationError,
    PayloadTooLargeError,
    NotFoundError,
    ConflictError,
    ExternalServiceError,
    RateLimitError,
)

logger = logging.getLogger(__name__)


class JobOrchestrationService:
    """Orchestrates job creation, retry, CSV export, and session deletion.

    Keeps HTTP concerns in routers; raises HTTPException on user errors for now.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self._store = FirestoreService()
        self._gcs = GCSService(self.settings.GCS_BUCKET)
        self._tasks = CloudTasksService(
            TasksConfig(
                project=self.settings.GCP_PROJECT,
                region=self.settings.REGION,
                queue=self.settings.TASKS_QUEUE,
                target_url=self.settings.TASKS_TARGET_URL,
                service_account_email=self.settings.TASKS_SERVICE_ACCOUNT_EMAIL,
                emulate=self.settings.TASKS_EMULATE,
            )
        )
        self._limiter = RateLimiterService()

    async def create_upload_jobs(self, session_id: str, files: List[UploadFile], *, client_ip: str | None = None) -> List[JobItem]:
        """Validate, upload, create Firestore jobs, and enqueue tasks.

        Returns a list of JobItem objects.
        """
        if not files:
            raise FileValidationError("No files provided")

        if len(files) > self.settings.MAX_FILES:
            # Treat as a rate/limits breach
            raise RateLimitError("Too many files in one request")

        # App-level rate limiting
        # Allow RateLimiterService to raise HTTPException with headers; do not intercept here.
        self._limiter.enforce_upload(session_id=session_id, files_count=len(files), client_ip=client_ip or "")

        job_items: List[JobItem] = []

        for f in files:
            if f.content_type not in self.settings.ACCEPTED_MIME:
                raise FileValidationError(f"Unsupported MIME type: {f.content_type}")

            file_bytes = await f.read()
            if not file_bytes:
                raise FileValidationError(f"File {f.filename} is empty")

            size_bytes = len(file_bytes)
            if size_bytes > self.settings.MAX_SIZE_MB * 1024 * 1024:
                raise PayloadTooLargeError(f"File {f.filename} exceeds size limit")

            try:
                page_count = count_pdf_pages(file_bytes)
            except HTTPException as e:
                # Normalize to domain exception for consistent router mapping
                raise FileValidationError(e.detail if hasattr(e, "detail") else "Invalid PDF")
            if page_count > self.settings.MAX_PAGES:
                raise FileValidationError(f"File {f.filename} exceeds page limit")

            job_id = str(uuid.uuid4())
            blob_path = f"uploads/{session_id}/{job_id}.pdf"
            try:
                gcs_uri = self._gcs.upload_bytes(blob_path, file_bytes, content_type="application/pdf")
            except Exception as exc:
                logger.error("[%s] GCS upload failed: %s", session_id, exc)
                raise ExternalServiceError("Storage error while uploading file")

            # Create Firestore job document
            self._store.create_job(
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
            try:
                self._tasks.enqueue_job(job_id, session_id)
            except Exception as exc:
                logger.error("[%s] Cloud Tasks enqueue failed for job %s: %s", session_id, job_id, exc)
                raise ExternalServiceError("Task queue error while enqueuing job")
            self._store.set_job_status(job_id, "queued", "queued")

            # Local emulation: if TASKS_EMULATE is true, process asynchronously without Cloud Tasks
            if self.settings.TASKS_EMULATE:
                # Use pipeline service directly to avoid router imports
                from .task_pipeline import TaskPipelineService

                asyncio.create_task(TaskPipelineService().process_invoice_job(job_id, session_id))

            job_items.append(
                JobItem(
                    jobId=job_id,
                    filename=f.filename,
                    status="queued",
                    sizeBytes=size_bytes,
                    pageCount=page_count,
                )
            )

        return job_items

    async def retry_job(self, job_id: str, session_id: str) -> None:
        job = self._store.get_job(job_id)
        if not job or job.get("sessionId") != session_id:
            raise NotFoundError("Job not found")

        gcs_uri: str = job.get("gcsUri", "")
        prefix = f"gs://{self.settings.GCS_BUCKET}/"
        if gcs_uri.startswith(prefix):
            blob_path = gcs_uri[len(prefix) :]
            exists = self._gcs.blob_exists(blob_path)
        else:
            exists = False

        if not exists:
            raise ConflictError("Original PDF not available; re-upload required")

        self._tasks.enqueue_job(job_id, session_id)
        self._store.set_job_status(job_id, "queued", "queued")
        # Increment manual retry counter (best-effort)
        try:
            from google.cloud.firestore_v1 import Increment

            self._store.update_job(job_id, {"manualRetries": Increment(1)})
        except Exception:
            pass

        if self.settings.TASKS_EMULATE:
            from .task_pipeline import TaskPipelineService

            asyncio.create_task(TaskPipelineService().process_invoice_job(job_id, session_id))

    async def get_session_jobs_as_csv(self, session_id: str) -> bytes:
        docs = self._store.list_done_jobs_by_session(session_id)
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

        # Serialize to CSV bytes
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
        return output.getvalue().encode("utf-8")

    async def delete_session_data(self, session_id: str) -> int:
        docs = self._store.list_jobs_by_session(session_id)
        deleted = 0
        for d in docs:
            gcs_uri: str = d.get("gcsUri", "")
            try:
                prefix = f"gs://{self.settings.GCS_BUCKET}/"
                if gcs_uri.startswith(prefix):
                    blob_path = gcs_uri[len(prefix) :]
                    self._gcs.delete_blob(blob_path)
            except Exception:
                pass
            try:
                self._store.delete_job(d.get("jobId"))
                deleted += 1
            except Exception:
                pass
        return deleted
