# AI Invoice Processing App

AI-powered invoice processing workflow that turns invoices in PDFs into structured data (HTML table and CSV export). It's designed to handle invoices in English and Dutch and extract key information such as invoice number, date, amount, line items and other relevant details.

## What it does
- Upload one or more PDF invoices.
- The app extracts text (OCR) and interprets it with an LLM.
- Results appear in a table; you can export them to CSV.

## How it works
1) Frontend calls the API via Google Cloud API Gateway (e.g., `https://<gateway-host>/api/...`).
2) Backend uploads files to Cloud Storage and creates job records in Firestore.
3) A background worker (Cloud Tasks + OIDC) triggers OCR with Vision, then parses
   the text using Gemini (primary) or OpenRouter (fallback).
4) When a job is done, the frontend polls and shows results; you can export or
   clear a session at any time.

![Workflow](diagram.png)

## Tech stack
- Frontend: Next.js on Firebase Hosting. Calls API via Google Cloud API Gateway (`NEXT_PUBLIC_API_BASE_URL`). Firebase Hosting `/api` rewrite has been removed.
- Backend: FastAPI on Cloud Run (requires authentication). Public entrypoint is API Gateway; Cloud Run only accepts calls from API Gateway SA and Cloud Tasks SA.
- Storage & DB: Cloud Storage (PDFs), Firestore (jobs + results)
- Queue/Async: Cloud Tasks
- OCR & AI: Google Cloud Vision OCR, Gemini; OpenRouter as fallback LLM

Tip: See below for developer notes if you want to run or extend the project.

## Privacy & security

We keep things simple and respectful of your data.

- PDFs are stored in Google Cloud Storage only long enough to process them.
  When you clear a session (Delete), we remove the files and related job docs right away
  in `backend/app/routers/jobs.py::delete_session()`.
- There’s also a small housekeeping loop (see `RETENTION_*` settings in `backend/app/main.py`)
  that cleans up stale sessions automatically after a time window.
- The background worker endpoint `POST /api/tasks/process` is not public: Cloud Tasks calls it
  using OIDC, and we verify that token in `backend/app/deps.py::verify_oidc_token()`.
- The public API is locked down with practical limits (max files, size, and page counts) and
  strict PDF checks to reduce abuse.
- CORS is restricted to our front‑end origins from `settings.CORS_ORIGINS`, so browsers can’t
  call the API from random sites.

Bottom line: no processed data is kept on the server once you end your session or hit refresh/clear,
and old sessions are automatically purged after a short retention window.

## Production configuration (summary)

- API Gateway is the public entrypoint. Cloud Run requires authentication and accepts calls only from:
  - API Gateway service account (frontend traffic)
  - Cloud Tasks service account (worker calls)
- Frontend reads `NEXT_PUBLIC_API_BASE_URL` (set via GitHub Actions secret `API_GATEWAY_BASE_URL`).
- Firebase Hosting `/api` rewrite has been removed; the frontend calls the Gateway host directly.
- API Gateway OpenAPI spec lives at `backend/openapi-gateway.yaml` (moved from `infra/`).

## Rate limiting & UX

- App-level limits (configurable via `RL_*` in backend):
  - Per-session: jobs/min, files/min, retries/min
  - Daily caps: per-session and global (CET fixed +1 for reset)
  - Optional per-IP backstop
- 429 responses include `Retry-After` and `X-RateLimit-*` headers.
- Frontend shows unified toast notifications during cooldown; only the affected control is disabled. CET-based daily reset still applies.
- Only the affected control is disabled during cooldown (Upload or Retry).
- Manual retry cap per job: 3 (further retries are rejected).

## Reliability & performance

- Async LLM calls: The backend uses `httpx` with timeouts and retries so slow AI calls don’t block other requests.
- Server-side sorting: Firestore now handles filtering and ordering for “done” jobs using a composite index
  (`sessionId`, `status`, `createdAt DESC`), which scales better than sorting in code.
- Resilient workers: A stale‑lock takeover lets a healthy worker reclaim jobs stuck in `processing` if another
  worker crashes. We also send light “heartbeats” during long stages so you can observe progress.
- Tiered OCR: Vision-only. Uses synchronous Vision for short scans (≤ OCR_SYNC_MAX_PAGES) and falls back to asynchronous Vision for larger PDFs.
- Sanitizer preprocessing: Lightweight, line‑preserving sanitization (configurable top/bottom strip, noise removal, smart truncation) before the LLM.


## Endpoints

- POST `/api/jobs` — upload 1..N PDFs, validate, upload to GCS, create Firestore docs, enqueue Cloud Task (emulated by default locally). Returns job IDs.
- GET `/api/jobs/{jobId}` — job status and result when available.
- GET `/api/sessions/{sessionId}/jobs` — list jobs for a session (requires matching X-Session-Id header).
- POST `/api/jobs/{jobId}/retry` — retry a job if original PDF still exists; 409 if re-upload needed.
- GET `/api/sessions/{sessionId}/export.csv` — export combined CSV for all done jobs in session.
- DELETE `/api/sessions/{sessionId}` — delete all jobs in a session and their PDFs immediately.
- POST `/api/tasks/process` — Cloud Tasks worker endpoint (Gemini primary, OpenRouter fallback). In production, secure with OIDC audience verification.
- GET `/api/config` — runtime limits and accepted MIME types.
- GET `/api/healthz` — health check.

