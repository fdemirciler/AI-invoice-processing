# AI Invoice Processing

AI-powered invoice reader that turns your PDFs into structured data.

What it does
- Upload one or more PDF invoices.
- The app extracts text (OCR) and interprets it with an LLM.
- Results appear in a table; you can export them to CSV.

How it works (see diagram below)
1) Frontend sends `POST /api/jobs` with your PDFs.
2) Backend uploads files to Cloud Storage and creates job records in Firestore.
3) A background worker (Cloud Tasks + OIDC) triggers OCR with Vision, then parses
   the text using Gemini (primary) or OpenRouter (fallback).
4) When a job is done, the frontend polls and shows results; you can export or
   clear a session at any time.

![Workflow](image.png)

Tech stack
- Frontend: Next.js on Firebase Hosting (same-origin `/api` rewrite)
- Backend: FastAPI on Cloud Run (public for app endpoints; worker secured by OIDC)
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

## Reliability & performance

- Async LLM calls: The backend uses `httpx` with timeouts and retries so slow AI calls don’t block other requests.
- Server-side sorting: Firestore now handles filtering and ordering for “done” jobs using a composite index
  (`sessionId`, `status`, `createdAt DESC`), which scales better than sorting in code.
- Resilient workers: A stale‑lock takeover lets a healthy worker reclaim jobs stuck in `processing` if another
  worker crashes. We also send light “heartbeats” during long stages so you can observe progress.

## Local Development

1) Create and activate a virtual environment

```bash
python -m venv .venv
. .venv/Scripts/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
```

2) Install dependencies

```bash
pip install -r requirements.txt
```

3) Configure environment (optional for local)

Copy `.env.example` to `.env` and adjust values. The app reads environment variables directly.

4) Run the server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

Open http://localhost:8080/docs for Swagger UI.

## Configuration

Environment variables (defaults shown):
- CORS_ORIGINS="*"  (comma-separated list)
- MAX_FILES=10
- MAX_SIZE_MB=10
- MAX_PAGES=20
- GCS_BUCKET=invoice_processing_storage
- REGION=europe-west4
- GCP_PROJECT=
- TASKS_QUEUE=invoice-process-queue
- TASKS_TARGET_URL=
- TASKS_SERVICE_ACCOUNT_EMAIL=
- TASKS_EMULATE=true  # set to false in Cloud Run with proper values above

# LLM
- GEMINI_API_KEY=
- GEMINI_MODEL=gemini-2.5-flash
- OPENROUTER_API_KEY=
- OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct:free

# OCR language hints
- OCR_LANG_HINTS=en,nl

# Retention
- RETENTION_HOURS=24
- RETENTION_LOOP_ENABLE=true
- RETENTION_LOOP_INTERVAL_MIN=60

For local development, .env is auto-loaded (using python-dotenv). You can keep `.env` either at repo root or under `backend/`.

### GCP auth for local

To use GCS/Firestore locally, authenticate with a service account or ADC:

```powershell
# Option 1: service account JSON
$env:GOOGLE_APPLICATION_CREDENTIALS = "C:\path\to\sa.json"

# Option 2: gcloud application default credentials
gcloud auth application-default login
```

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

