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

Example upload (PowerShell/curl):

```powershell
$sid = [guid]::NewGuid().ToString()
curl -X POST "http://localhost:8080/api/jobs" ^
  -H "X-Session-Id: $sid" ^
  -F "files=@C:\invoices\sample1.pdf;type=application/pdf" ^
  -F "files=@C:\invoices\sample2.pdf;type=application/pdf"
```

Check job status:

```powershell
curl -s "http://localhost:8080/api/jobs/<jobId>" -H "X-Session-Id: $sid" | jq .
```

Export CSV when done:

```powershell
curl -L "http://localhost:8080/api/sessions/$sid/export.csv" -H "X-Session-Id: $sid" -o export.csv
```

Trigger worker manually when TASKS_EMULATE=true (local):

```powershell
curl -X POST "http://localhost:8080/api/tasks/process" ^
  -H "Content-Type: application/json" ^
  -d '{"jobId":"<jobId>","sessionId":"'"$sid"'"}'
```

## Deploy to Cloud Run (step-by-step)

1) Prerequisites

- gcloud CLI installed and logged in: `gcloud auth login`
- Set project and region (we use europe-west4):
  ```bash
  gcloud config set project <PROJECT_ID>
  gcloud config set run/region europe-west4
  ```
- Enable APIs: Run, Artifact Registry, Cloud Build, Firestore, Vision, Cloud Tasks, Secret Manager:
  ```bash
  gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com \
    firestore.googleapis.com vision.googleapis.com cloudtasks.googleapis.com secretmanager.googleapis.com
  ```

2) Build and push the container

Option A — Docker to Artifact Registry:
```bash
REGION=europe-west4
REPO=invoice-backend
IMAGE=${REGION}-docker.pkg.dev/$(gcloud config get-value project)/${REPO}/backend:v1
gcloud artifacts repositories create ${REPO} --repository-format=docker --location=${REGION} --description="Backend" || true
gcloud auth configure-docker ${REGION}-docker.pkg.dev -q
docker build -t ${IMAGE} ./backend
docker push ${IMAGE}
```

Option B — Source deploy (no Docker push):
```bash
gcloud run deploy invoice-backend --source ./backend --region europe-west4
```

3) Create/select a runtime service account (recommended)

```bash
SA=invoice-backend-sa
gcloud iam service-accounts create ${SA} --display-name "Invoice Backend SA" || true
RUNTIME_SA=${SA}@$(gcloud config get-value project).iam.gserviceaccount.com
```

Grant minimum roles:
```bash
gcloud projects add-iam-policy-binding $(gcloud config get-value project) \
  --member=serviceAccount:${RUNTIME_SA} --role=roles/firestore.user
gcloud projects add-iam-policy-binding $(gcloud config get-value project) \
  --member=serviceAccount:${RUNTIME_SA} --role=roles/storage.objectAdmin
gcloud projects add-iam-policy-binding $(gcloud config get-value project) \
  --member=serviceAccount:${RUNTIME_SA} --role=roles/vision.user
gcloud projects add-iam-policy-binding $(gcloud config get-value project) \
  --member=serviceAccount:${RUNTIME_SA} --role=roles/cloudtasks.enqueuer
gcloud projects add-iam-policy-binding $(gcloud config get-value project) \
  --member=serviceAccount:${RUNTIME_SA} --role=roles/secretmanager.secretAccessor
```

4) Deploy to Cloud Run

Using the pushed image (Option A):
```bash
gcloud run deploy invoice-backend \
  --image ${IMAGE} \
  --region europe-west4 \
  --service-account ${RUNTIME_SA} \
  --concurrency 10 \
  --cpu 1 --memory 1Gi \
  --timeout 900 \
  --no-allow-unauthenticated
```

Note: We recommend keeping the service authenticated. Grant invoker to only trusted identities (e.g., Cloud Tasks SA, your frontend if needed). If you want public access to docs/health locally, you can temporarily allow unauthenticated.

Set environment variables (example):
```bash
gcloud run services update invoice-backend --region europe-west4 \
  --set-env-vars CORS_ORIGINS="*",MAX_FILES=10,MAX_SIZE_MB=10,MAX_PAGES=20 \
  --set-env-vars GCP_PROJECT=$(gcloud config get-value project),REGION=europe-west4,GCS_BUCKET=invoice_processing_storage,FIRESTORE_DATABASE_ID="(default)" \
  --set-env-vars TASKS_QUEUE=invoice-process-queue,TASKS_TARGET_URL=,TASKS_SERVICE_ACCOUNT_EMAIL=,TASKS_EMULATE=false \
  --set-env-vars GEMINI_MODEL=gemini-2.5-flash,OPENROUTER_MODEL="meta-llama/llama-3.3-70b-instruct:free" \
  --set-env-vars OCR_LANG_HINTS="en,nl",RETENTION_HOURS=24,RETENTION_LOOP_ENABLE=true,RETENTION_LOOP_INTERVAL_MIN=60
```
For API keys, prefer Secret Manager and mount as env vars:
```bash
gcloud run services update invoice-backend --region europe-west4 \
  --update-secrets GEMINI_API_KEY=gemini-api-key:latest,OPENROUTER_API_KEY=openrouter-api-key:latest
```

5) Configure Cloud Tasks with OIDC

- Create or reuse a queue in europe-west4:
  ```bash
  gcloud tasks queues create invoice-process-queue --location europe-west4 || true
  ```
- Create a dedicated Cloud Tasks caller service account (optional but recommended):
  ```bash
  TASKS_SA=invoice-tasks-caller
  gcloud iam service-accounts create ${TASKS_SA} --display-name "Tasks Caller" || true
  TASKS_SA_EMAIL=${TASKS_SA}@$(gcloud config get-value project).iam.gserviceaccount.com
  ```
- Grant it Cloud Run Invoker on the service (for OIDC tokens to be accepted):
  ```bash
  gcloud run services add-iam-policy-binding invoice-backend \
    --member=serviceAccount:${TASKS_SA_EMAIL} --role=roles/run.invoker --region europe-west4
  ```
- Set these env vars on the service:
  - `TASKS_EMULATE=false`
  - `TASKS_TARGET_URL=https://<CLOUD_RUN_URL>/api/tasks/process`
  - `TASKS_SERVICE_ACCOUNT_EMAIL=${TASKS_SA_EMAIL}`

6) Verify deployment

Get the service URL:
```bash
URL=$(gcloud run services describe invoice-backend --region europe-west4 --format='value(status.url)')
echo $URL
```

- Health check: `curl -s "$URL/api/healthz" | jq .`
- Config: `curl -s "$URL/api/config" | jq .`
- Upload a PDF (PowerShell example):
  ```powershell
  $sid = [guid]::NewGuid().ToString()
  curl -X POST "$URL/api/jobs" -H "X-Session-Id: $sid" -F "files=@C:\invoices\sample1.pdf;type=application/pdf"
  ```
- The worker will be invoked by Cloud Tasks. Poll job status via `GET $URL/api/jobs/{jobId}` and export CSV via `GET $URL/api/sessions/{sessionId}/export.csv`.

7) Notes

- Consider adding composite Firestore indexes in production for any ordered queries and re-introduce server-side ordering once indexes are in place.
- Logs and metrics are available in Cloud Run Logs Explorer. Increase CPU/memory/timeouts if OCR/LLM workloads are heavy.
