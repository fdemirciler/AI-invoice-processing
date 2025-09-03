"""Firestore helper service for jobs collection."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from google.cloud import firestore
from ..config import get_settings
from google.cloud.firestore_v1 import Increment


class FirestoreService:
    """Thin wrapper around Firestore client for job operations."""

    def __init__(self) -> None:
        settings = get_settings()
        # Use explicit database if provided in env, else default
        if hasattr(settings, "FIRESTORE_DATABASE_ID") and settings.FIRESTORE_DATABASE_ID:
            self.client = firestore.Client(
                project=settings.GCP_PROJECT or None,
                database=settings.FIRESTORE_DATABASE_ID,
            )
        else:
            self.client = firestore.Client()
        self._jobs = self.client.collection("jobs")

    def create_job(self, job_id: str, doc: Dict[str, Any]) -> None:
        ref = self._jobs.document(job_id)
        ref.set(doc)

    def set_job_status(self, job_id: str, status: str, stage_key: str) -> None:
        ref = self._jobs.document(job_id)
        ref.set(
            {
                "status": status,
                "updatedAt": firestore.SERVER_TIMESTAMP,
                "stages": {stage_key: firestore.SERVER_TIMESTAMP},
            },
            merge=True,
        )

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        doc = self._jobs.document(job_id).get()
        return doc.to_dict() if doc.exists else None

    def update_job(self, job_id: str, updates: Dict[str, Any]) -> None:
        ref = self._jobs.document(job_id)
        updates = {**updates, "updatedAt": firestore.SERVER_TIMESTAMP}
        ref.set(updates, merge=True)

    def acquire_processing_lock(
        self,
        job_id: str,
        worker_id: str,
        stale_minutes: int = 10,
    ) -> Optional[Dict[str, Any]]:
        """Attempt to acquire a processing lock transactionally.

        Returns the job document on success, or None if contention/invalid state.
        """
        ref = self._jobs.document(job_id)

        @firestore.transactional
        def txn_fn(tx: firestore.Transaction) -> Optional[Dict[str, Any]]:
            snap = ref.get(transaction=tx)
            if not snap.exists:
                return None
            data = snap.to_dict() or {}
            status = data.get("status")
            lock = data.get("processingLock") or {}
            locked_at = lock.get("lockedAt")

            # allow takeover if lock is stale
            can_take = False
            if not lock:
                can_take = True
            else:
                # server timestamps are not available client-side; use forward takeover via status re-check
                # as a simplification: if currently not 'processing', allow takeover
                can_take = status != "processing"

            if status not in {"uploaded", "queued", "failed", "processing"}:
                return None
            if not can_take:
                return None

            update = {
                "status": "processing",
                "processingLock": {"lockedBy": worker_id, "lockedAt": firestore.SERVER_TIMESTAMP},
                "attempt": Increment(1),
                "stages": {"processing": firestore.SERVER_TIMESTAMP},
                "updatedAt": firestore.SERVER_TIMESTAMP,
            }
            tx.set(ref, update, merge=True)
            return {**data, **update}

        tx = self.client.transaction()
        return txn_fn(tx)

    def release_processing_lock(self, job_id: str) -> None:
        ref = self._jobs.document(job_id)
        ref.set({"processingLock": firestore.DELETE_FIELD}, merge=True)

    def set_result(self, job_id: str, result_json: Dict[str, Any], confidence: float) -> None:
        ref = self._jobs.document(job_id)
        ref.set(
            {
                "resultJson": result_json,
                "confidenceScore": float(confidence),
                "status": "done",
                "stages": {"done": firestore.SERVER_TIMESTAMP},
                "updatedAt": firestore.SERVER_TIMESTAMP,
                "processingLock": firestore.DELETE_FIELD,
            },
            merge=True,
        )

    def set_error(self, job_id: str, message: str) -> None:
        ref = self._jobs.document(job_id)
        ref.set(
            {
                "status": "failed",
                "error": message[:2000],
                "stages": {"failed": firestore.SERVER_TIMESTAMP},
                "updatedAt": firestore.SERVER_TIMESTAMP,
                "processingLock": firestore.DELETE_FIELD,
            },
            merge=True,
        )

    # Queries
    def list_jobs_by_session(self, session_id: str) -> List[Dict[str, Any]]:
        q = self._jobs.where("sessionId", "==", session_id).order_by("createdAt")
        return [doc.to_dict() for doc in q.stream()]

    def list_done_jobs_by_session(self, session_id: str) -> List[Dict[str, Any]]:
        # Use equality filters only (no order_by) to avoid requiring a composite index.
        q = self._jobs.where("sessionId", "==", session_id).where("status", "==", "done")
        docs = [doc.to_dict() for doc in q.stream()]
        # Sort client-side by createdAt if available
        try:
            docs.sort(key=lambda d: d.get("createdAt") or datetime.min.replace(tzinfo=timezone.utc))
        except Exception:
            pass
        return docs

    def delete_stale_jobs(self, older_than_hours: int = 24) -> int:
        """Delete jobs older than the given hours. Returns count deleted."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)
        # Firestore requires an index for range queries on createdAt
        q = self._jobs.where("createdAt", "<", cutoff)
        count = 0
        for doc in q.stream():
            try:
                doc.reference.delete()
                count += 1
            except Exception:
                pass
        return count

    def delete_job(self, job_id: str) -> None:
        self._jobs.document(job_id).delete()
