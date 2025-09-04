# Invoice Processing Backend (FastAPI)

This is the backend service for the Invoice Processing Web App.

- Framework: FastAPI (Python 3.11)
- Runtime: Cloud Run (europe-west4)
- Async engine: Cloud Tasks (HTTP target)
- OCR: Google Cloud Vision (PDF OCR via GCS)
- LLM: Gemini 2.5 Flash (primary); OpenRouter fallback

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

