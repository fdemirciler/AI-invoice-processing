from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import HTTPException
import httpx
from google.api_core.exceptions import GoogleAPIError
from google.cloud import firestore
from pydantic import ValidationError

from ...config import get_settings
from ...models import Invoice
from ...services.firestore import FirestoreService
from ...services.gcs import GCSService
from ...services.llm import LLMService
from ...services.vision import VisionService
from ...pipeline.preprocessing import sanitize_for_llm
from ...pipeline.evaluation import compute_confidence

logger = logging.getLogger(__name__)


class TaskPipelineService:
    """Owns the execution of a single job's processing pipeline."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.store = FirestoreService()
        self.gcs = GCSService(self.settings.GCS_BUCKET)
        self.vision = VisionService(self.settings.GCS_BUCKET)
        self.llm = LLMService()
        self.worker_id = "tasks-worker"  # TODO: derive from hostname or env if needed

    async def process_invoice_job(self, job_id: str, session_id: str) -> Dict[str, Any]:
        # Acquire processing lock; if not obtained, return 200 to avoid retry storms
        locked = self.store.acquire_processing_lock(
            job_id, worker_id=self.worker_id, stale_minutes=self.settings.LOCK_STALE_MINUTES
        )
        if not locked:
            logger.info("[%s][%s] lock not acquired", job_id, self.worker_id)
            return {"ok": True, "jobId": job_id, "note": "lock not acquired; likely processed by another worker"}

        try:
            # Heartbeat: lock acquired
            try:
                self.store.update_job(job_id, {"stages": {"heartbeat": firestore.SERVER_TIMESTAMP}})
            except Exception:
                pass

            job = self.store.get_job(job_id)
            if not job:
                raise HTTPException(status_code=404, detail="Job not found")
            if job.get("sessionId") != session_id:
                raise HTTPException(status_code=400, detail="sessionId mismatch")

            gcs_uri: str = job.get("gcsUri", "")
            if not gcs_uri.startswith("gs://"):
                self.store.set_error(job_id, "Missing GCS URI for job")
                return {"ok": False, "jobId": job_id, "error": "missing gcsUri"}

            # OCR stage
            self.store.set_job_status(job_id, "extracting", "extracting")
            try:
                self.store.update_job(job_id, {"stages": {"heartbeat": firestore.SERVER_TIMESTAMP}})
            except Exception:
                pass
            temp_prefix = f"gs://{self.settings.GCS_BUCKET}/vision/{job_id}/"
            page_count = job.get("pageCount", self.settings.MAX_PAGES)
            ocr = self.vision.ocr_pdf_from_gcs(
                gcs_uri,
                temp_prefix=temp_prefix,
                batch_size=min(page_count, self.settings.MAX_PAGES),
                page_count=page_count,
            )
            try:
                self.store.update_job(job_id, {"ocrMethod": ocr.method})
            except Exception:
                pass
            logger.info("[%s][%s] OCR method: %s", job_id, self.worker_id, getattr(ocr, "method", "unknown"))
            try:
                self.store.update_job(job_id, {"stages": {"heartbeat": firestore.SERVER_TIMESTAMP}})
            except Exception:
                pass

            # Preprocess via sanitizer
            raw_text = ocr.text or ""
            raw_token_proxy = len(raw_text.split())
            preproc_stats = {"reduction": 0.0}
            text_for_llm = sanitize_for_llm(
                raw_text,
                self.settings.PREPROCESS_MAX_CHARS,
                self.settings.ZONE_STRIP_TOP,
                self.settings.ZONE_STRIP_BOTTOM,
            )
            base = max(1, len(raw_text))
            preproc_stats["reduction"] = round(max(0.0, 1.0 - (len(text_for_llm) / float(base))), 3)
            sanitized_token_proxy = len(text_for_llm.split())
            logger.info(
                "[%s][%s] Sanitization metrics - raw_tokens=%s, sanitized_tokens=%s",
                job_id,
                self.worker_id,
                raw_token_proxy,
                sanitized_token_proxy,
            )

            # LLM extraction
            self.store.set_job_status(job_id, "llm", "llm")
            try:
                self.store.update_job(job_id, {"stages": {"heartbeat": firestore.SERVER_TIMESTAMP}})
            except Exception:
                pass
            parsed = await self.llm.extract_invoice_async(text_for_llm)
            try:
                self.store.update_job(job_id, {"stages": {"heartbeat": firestore.SERVER_TIMESTAMP}})
            except Exception:
                pass

            # Validate & coerce
            invoice = Invoice.model_validate_jsonish(parsed)

            # Confidence score
            confidence = compute_confidence(
                ocr_text=text_for_llm, pages=ocr.pages or job.get("pageCount", 1), inv=invoice
            )

            # Persist result
            self.store.set_result(
                job_id,
                result_json=invoice.model_dump(mode="json"),
                confidence=confidence,
            )
            # Save lightweight preprocessing stats only (no payload storage)
            try:
                self.store.update_job(job_id, {"preprocess": preproc_stats})
            except Exception:
                pass

            # Cleanup input PDF (best-effort)
            try:
                prefix = f"gs://{self.settings.GCS_BUCKET}/"
                if gcs_uri.startswith(prefix):
                    blob_path = gcs_uri[len(prefix) :]
                    self.gcs.delete_blob(blob_path)
            except Exception:
                pass

            return {"ok": True, "jobId": job_id, "status": "done", "confidence": confidence}

        except ValidationError as exc:
            try:
                err_details = exc.errors()
            except Exception:
                err_details = []
            try:
                preview = {
                    "subtotal": parsed.get("subtotal") if isinstance(parsed, dict) else None,
                    "tax": parsed.get("tax") if isinstance(parsed, dict) else None,
                    "total": parsed.get("total") if isinstance(parsed, dict) else None,
                    "lineItemsCount": len(parsed.get("lineItems") or []) if isinstance(parsed, dict) else None,
                }
            except Exception:
                preview = None
            logger.error("[%s] validation error: %s | details=%s | preview=%s", job_id, exc, err_details, preview)
            self.store.set_error(job_id, "Validation error: invoice schema mismatch (see logs)")
            return {"ok": False, "jobId": job_id, "error": "validation error"}

        except (httpx.RequestError, httpx.HTTPStatusError) as exc:
            logger.error("[%s] network/LLM error: %s", job_id, exc)
            self.store.set_error(job_id, "Transient API error, will retry")
            return {"ok": False, "jobId": job_id, "error": "transient api error"}

        except (Exception,) as exc:
            # Preserve specific HTTP and GCP exceptions semantics similar to prior code
            if isinstance(exc, (HTTPException,)):
                logger.error("[%s] http error: %s", job_id, getattr(exc, "detail", str(exc)))
                self.store.set_error(job_id, getattr(exc, "detail", "HTTP error"))
                raise
            if isinstance(exc, GoogleAPIError):
                logger.error("[%s] GCP service error: %s", job_id, exc)
                self.store.set_error(job_id, "Storage or Firestore error")
                return {"ok": False, "jobId": job_id, "error": "gcp service error"}
            logger.exception("[%s] unexpected error", job_id)
            self.store.set_error(job_id, "Unexpected internal error")
            return {"ok": False, "jobId": job_id, "error": "unexpected error"}

        finally:
            # Always release the lock to avoid stuck jobs
            try:
                self.store.release_processing_lock(job_id)
            except Exception:
                pass
