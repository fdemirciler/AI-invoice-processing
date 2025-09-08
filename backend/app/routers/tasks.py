"""Tasks worker endpoint: processes a single job end-to-end.

Pipeline: Acquire lock -> OCR -> preprocess -> LLM -> validate -> score -> persist -> cleanup.
Includes granular error handling and always releases the processing lock.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict
import logging
from pydantic import ValidationError
import httpx
from google.api_core.exceptions import GoogleAPIError

from fastapi import APIRouter, Depends, HTTPException
from google.cloud import firestore

from ..config import get_settings
from ..deps import verify_oidc_token
from ..models import Invoice
from ..services.firestore import FirestoreService
from ..services.gcs import GCSService
from ..services.llm import LLMService
from ..services.vision import VisionService

router = APIRouter(prefix="/tasks", tags=["tasks"])  # mounted under /api
logger = logging.getLogger(__name__)


def _normalize_text(text: str) -> str:
    # Basic normalization: NFKC, collapse whitespace, strip
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _compute_confidence(ocr_text: str, pages: int, inv: Invoice) -> float:
    # OCR quality: chars per page heuristic
    pages = max(1, pages)
    ocr_quality = min(1.0, len(ocr_text) / float(pages * 800))

    # LLM validity: if we have a validated Invoice, assume high
    llm_validity = 1.0

    # Consistency: subtotal + tax ~ total; sum(lineTotals) ~ subtotal
    def closeness(expected: float, actual: float) -> float:
        if expected <= 0:
            return 0.0
        return max(0.0, 1.0 - min(abs(actual - expected) / expected, 1.0))

    sum_lines = sum(li.lineTotal for li in inv.lineItems) if inv.lineItems else 0.0
    c1 = closeness(inv.subtotal + inv.tax, inv.total)
    c2 = closeness(inv.subtotal, sum_lines)
    consistency = (c1 + c2) / 2.0

    # Coverage: how many key fields present
    fields_present = 0
    total_fields = 8
    fields_present += 1 if inv.invoiceNumber else 0
    fields_present += 1 if inv.invoiceDate else 0
    fields_present += 1 if inv.vendorName else 0
    fields_present += 1 if inv.currency else 0
    fields_present += 1 if inv.subtotal is not None else 0
    fields_present += 1 if inv.tax is not None else 0
    fields_present += 1 if inv.total is not None else 0
    fields_present += 1 if inv.lineItems else 0
    coverage = fields_present / float(total_fields)

    score = 0.4 * ocr_quality + 0.3 * llm_validity + 0.2 * consistency + 0.1 * coverage
    return round(score, 3)


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

    settings = get_settings()
    store = FirestoreService()
    gcs = GCSService(settings.GCS_BUCKET)
    vision = VisionService(settings.GCS_BUCKET)
    llm = LLMService()
    worker_id = "tasks-worker"  # TODO: derive from hostname or env if needed

    # Acquire processing lock (idempotent). If cannot acquire, return 200 to avoid retries storm.
    locked = store.acquire_processing_lock(
        job_id, worker_id=worker_id, stale_minutes=settings.LOCK_STALE_MINUTES
    )
    if not locked:
        logger.info("[%s][%s] lock not acquired", job_id, worker_id)
        return {"ok": True, "jobId": job_id, "note": "lock not acquired; likely processed by another worker"}

    # Read job data and process inside a guarded block to ensure lock is released
    try:
        # Heartbeat: lock acquired
        try:
            store.update_job(job_id, {"stages": {"heartbeat": firestore.SERVER_TIMESTAMP}})
        except Exception:
            pass

        job = store.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        if job.get("sessionId") != session_id:
            raise HTTPException(status_code=400, detail="sessionId mismatch")

        gcs_uri: str = job.get("gcsUri", "")
        if not gcs_uri.startswith("gs://"):
            store.set_error(job_id, "Missing GCS URI for job")
            return {"ok": False, "jobId": job_id, "error": "missing gcsUri"}

        # OCR stage
        store.set_job_status(job_id, "extracting", "extracting")
        try:
            store.update_job(job_id, {"stages": {"heartbeat": firestore.SERVER_TIMESTAMP}})
        except Exception:
            pass
        temp_prefix = f"gs://{settings.GCS_BUCKET}/vision/{job_id}/"
        page_count = job.get("pageCount", settings.MAX_PAGES)
        ocr = vision.ocr_pdf_from_gcs(
            gcs_uri,
            temp_prefix=temp_prefix,
            batch_size=min(page_count, settings.MAX_PAGES),
            page_count=page_count,
        )
        try:
            store.update_job(job_id, {"ocrMethod": ocr.method})
        except Exception:
            pass
        logger.info("[%s][%s] OCR method: %s", job_id, worker_id, getattr(ocr, "method", "unknown"))
        try:
            store.update_job(job_id, {"stages": {"heartbeat": firestore.SERVER_TIMESTAMP}})
        except Exception:
            pass

        # Preprocess text
        text_norm = _normalize_text(ocr.text)

        # LLM extraction stage
        store.set_job_status(job_id, "llm", "llm")
        try:
            store.update_job(job_id, {"stages": {"heartbeat": firestore.SERVER_TIMESTAMP}})
        except Exception:
            pass
        parsed = await llm.extract_invoice_async(text_norm)
        try:
            store.update_job(job_id, {"stages": {"heartbeat": firestore.SERVER_TIMESTAMP}})
        except Exception:
            pass

        # Validate & coerce
        invoice = Invoice.model_validate_jsonish(parsed)

        # Confidence score
        confidence = _compute_confidence(
            ocr_text=text_norm, pages=ocr.pages or job.get("pageCount", 1), inv=invoice
        )

        # Persist result (ensure JSON-serializable types for Firestore)
        store.set_result(
            job_id,
            result_json=invoice.model_dump(mode="json"),
            confidence=confidence,
        )

        # Cleanup input PDF (best-effort)
        try:
            prefix = f"gs://{settings.GCS_BUCKET}/"
            if gcs_uri.startswith(prefix):
                blob_path = gcs_uri[len(prefix) :]
                gcs.delete_blob(blob_path)
        except Exception:  # best-effort cleanup
            pass

        return {"ok": True, "jobId": job_id, "status": "done", "confidence": confidence}

    except ValidationError as exc:
        logger.error("[%s] validation error: %s", job_id, exc)
        store.set_error(job_id, f"Validation error: {str(exc)}")
        return {"ok": False, "jobId": job_id, "error": "validation error"}

    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        logger.error("[%s] network/LLM error: %s", job_id, exc)
        store.set_error(job_id, "Transient API error, will retry")
        return {"ok": False, "jobId": job_id, "error": "transient api error"}

    except GoogleAPIError as exc:
        logger.error("[%s] GCP service error: %s", job_id, exc)
        store.set_error(job_id, "Storage or Firestore error")
        return {"ok": False, "jobId": job_id, "error": "gcp service error"}

    except HTTPException as exc:
        # Preserve HTTP semantics but also mark the job as failed for traceability
        logger.error("[%s] http error: %s", job_id, exc.detail)
        store.set_error(job_id, exc.detail)
        # Re-raise so FastAPI still responds with proper status
        raise

    except Exception as exc:  # noqa: BLE001
        logger.exception("[%s] unexpected error", job_id)
        store.set_error(job_id, "Unexpected internal error")
        return {"ok": False, "jobId": job_id, "error": "unexpected error"}

    finally:
        # Always release the lock to avoid stuck jobs
        try:
            store.release_processing_lock(job_id)
        except Exception:
            pass
