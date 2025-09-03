Updated Plan: Cloud Tasks + Idempotent Worker
Incorporated your comments:

PDFs only; Vision PDF OCR requires GCS, so uploads always go to your existing bucket.
Replace Pub/Sub with Cloud Tasks for simpler async.
Add Firestore transactional locking and full idempotency across stages.
Key Changes
Async engine: Cloud Tasks queue (europe-west4) → HTTP target /api/tasks/process.
Statuses: uploaded → queued → processing → extracting → llm → done|failed.
Locking: Firestore transaction per job to acquire processingLock and enforce forward-only transitions.
Idempotency: Every stage checks persisted markers; safe to retry/endure duplicates.
Architecture
Backend: FastAPI on Cloud Run (europe-west4).
Async: Cloud Tasks triggers the same service (/api/tasks/process) with OIDC.
Storage: Your GCS bucket for transient PDFs + Vision outputs; immediate deletion after use.
State: Firestore for jobs and session scoping; TTL as safety.
LLM: Gemini 2.5 Flash primary; OpenRouter fallback.
Cloud Tasks
Queue: invoice-process-queue in europe-west4.
HTTP target: POST https://<cloud-run>/api/tasks/process.
Auth: OIDC token using the Cloud Run service account; verify audience.
Payload: { jobId, sessionId } (jobId is the dedup key in Firestore; task name can be auto).
Retries: maxAttempts 3–5; minBackoff 30s; maxBackoff 5m.
Timeout: Cloud Run request timeout 900s (initial); increase if needed.
Job Lifecycle + Idempotency
Create (POST /api/jobs):
Validate PDFs (MIME, size ≤10MB).
Count pages (≤20) before queueing.
Upload to GCS: gs://<bucket>/uploads/{sessionId}/{jobId}.pdf.
Create Firestore job: status=uploaded.
Enqueue Cloud Task: status → queued.
Worker (/api/tasks/process__)__:
Acquire lock (transaction):
Read job; ensure status ∈ {uploaded, queued, failed} and either no lock or stale.
Set processingLock = { lockedBy, lockedAt }, status=processing, upsert attempt++.
If tx fails (contention), exit 200 (idempotent no-op).
Vision OCR:
If visionOperationName missing:
Start asyncBatchAnnotateFiles with input gs://.../{jobId}.pdf and output gs://.../vision/{jobId}/.
Save visionOperationName; set status=extracting.
Poll operation until done (exponential backoff within timeout).
Parse Vision JSON output (read all shards), derive raw text.
Delete Vision output files (ignore 404).
Preprocess:
Normalize whitespace, trim headers/footers, cap size, lang hints [nl,en].
LLM:
If resultJson absent:
Call Gemini 2.5 Flash with strict JSON schema; on non-JSON or error, fallback to OpenRouter.
Validate and normalize numeric/date fields.
Confidence score:
Compute: 0.4*ocrQuality + 0.3*llmValidity + 0.2*consistency + 0.1*coverage.
Persist + Cleanup:
Save resultJson, confidenceScore, status=done, clear lock.
Delete input PDF from GCS (ignore 404).
On error:
Save status=failed, error, clear lock (best-effort), leave GCS clean.
Locking details:
Field: processingLock = { lockedBy: string, lockedAt: timestamp }.
Stale lock: if lockedAt older than N minutes (e.g., 10), a new worker may take over.
Forward-only transitions: reject regressions; all updates within transactions.
Stage idempotency:
Vision: if visionOperationName exists → resume polling; else create one.
Output parsing: reading + deleting is safe; ignore non-existent errors.
LLM: only call if resultJson not present.
Final delete: trigger even if already deleted.
Firestore Schema (collection jobs)
jobId, sessionId
filename, sizeBytes, pageCount
status: enum
stages: map of timestamps per stage
processingLock: {lockedBy, lockedAt}
attempt: integer
visionOperationName?: string
resultJson?: object
confidenceScore?: number
error?: string
createdAt, updatedAt
TTL on createdAt (safety only; session deletes are primary)
API Contract (Frontend Wiring)
Headers

X-Session-Id: required (frontend generates UUID per load, no persistence)
CORS: limited to your frontend origin(s)
POST /api/jobs (multipart)
files[]: 1..10 PDFs
202:
json
{
  "sessionId": "<uuid>",
  "jobs": [{"jobId":"...", "filename":"...", "status":"queued"}],
  "limits": {"maxFiles":10, "maxSizeMb":10, "maxPages":20}
}
GET /api/jobs/{jobId}
200:
json
{
  "jobId":"...",
  "status":"llm",
  "stages":{"uploaded":"...","queued":"...","processing":"...","extracting":"...","llm":"..."},
  "resultJson": null,
  "confidenceScore": null,
  "error": null
}
When done: status=done, include resultJson, confidenceScore.
GET /api/sessions/{sessionId}/jobs
List jobs for the current session.
POST /api/jobs/{jobId}/retry
If PDF already deleted and no cached OCR, returns 409 “re-upload required.”
GET /api/sessions/{sessionId}/export.csv
Combined CSV across all done jobs in the session.
DELETE /api/sessions/{sessionId}
Deletes all session jobs immediately (primary retention control).
GET /api/config and GET /api/healthz
Security & Ops
Cloud Tasks OIDC → verify JWT audience in /api/tasks/process.
Secrets from Secret Manager (Gemini, OpenRouter).
Cloud Run: europe-west4, concurrency 10–20, timeout 900s, min instances 0.
Logging with jobId correlation; metrics on attempts/failures.
CSV Columns (combined)
invoiceNumber, invoiceDate, vendorName, currency, subtotal, tax, total, dueDate,
lineItemIndex, description, quantity, unitPrice, lineTotal,
confidenceScore, filename