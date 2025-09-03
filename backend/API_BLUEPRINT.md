# The workflow is as follows:  

1. **File Upload** – User can upload one or multiple invoice PDFs at a time.  
2. **OCR Extraction** – Backend sends the files to **Google Vision AI** to extract raw text and/or structured document data.  
3. **Data Processing** – Extracted data is processed via a Python-based intermediary pipeline (e.g., regex cleaning, parsing, or pre-formatting for LLM input).  
4. **LLM Integration** – The cleaned data is passed to an LLM (Gemini via Google AI Studio or OpenRouter API). The LLM returns structured invoice information as **key-value pairs** (e.g., invoice number, date, vendor, line items, totals).  
5. **Frontend Display** – Structured output for all processed invoices is displayed in a clean, responsive table in the frontend. Each invoice can be viewed individually or in a combined results table.  
6. **Export** – User can download structured results as **CSV files** (one CSV per invoice or a combined CSV).  




# API Blueprint — Invoice Processing Backend

This document describes the backend API that the frontend will integrate with.
It summarizes endpoints, required headers, request/response models, statuses,
and usage patterns confirmed from the FastAPI routers in `backend/app/routers/`.

- Base URL prefix: `/api` (see `backend/app/main.py` and `backend/app/config.py`)
- Internal worker path: `/api/tasks/process` (for Cloud Tasks; the frontend should not call this)

---

## Session model

- The app is session-scoped via a per-tab UUID v4.
- The frontend must generate a UUID v4 on page load and attach it to every request header:
  - Header: `X-Session-Id: <uuid>`
- Validation regex: 36-char UUID pattern, enforced by `get_session_id()` in `backend/app/deps.py`.
- Missing/invalid `X-Session-Id` → HTTP 400.

---

## Authentication

- Cloud Run service may be deployed as authenticated. A SPA cannot directly mint an OIDC
  identity token, so pick one approach:
  - Allow unauthenticated access for a demo and rely on limits + session header.
  - Use a lightweight proxy/backend that adds the Cloud Run identity token and forwards requests.
  - Host the SPA behind the same identity context (e.g., IAP) and fetch with credentials.

---

## CORS

- Controlled by `CORS_ORIGINS` env (comma-separated). For local/dev `*` is acceptable.
  Narrow origins in production.

---

## Runtime config

GET `/api/config`

- Purpose: expose non-sensitive runtime limits and accepted MIME types.
- Response body (JSON):
  - `maxFiles: number`
  - `maxSizeMb: number`
  - `maxPages: number`
  - `acceptedMime: string[]` (e.g., `["application/pdf"]`)

Source: `backend/app/routers/config.py`

---

## Health

GET `/api/healthz`

- Simple liveness check. Returns `{ status: "ok", time: <ISO> }`.

Source: `backend/app/routers/health.py`

---

## Upload PDFs — create jobs

POST `/api/jobs`

- Headers:
  - `X-Session-Id: <uuid>`
- Content-Type: `multipart/form-data`
- Form fields:
  - Repeat `files` (one entry per PDF). Only `application/pdf` accepted.
- Validations:
  - Total files per request ≤ `maxFiles`
  - File size ≤ `maxSizeMb` MB
  - PDF pages ≤ `maxPages`
  - MIME must be accepted
- Status code: 202 Accepted
- Response body (JSON — `JobsCreateResponse`):
  - `sessionId: string`
  - `jobs: Array<{ jobId: string; filename: string; status: "queued" }>`
  - `limits: { maxFiles, maxSizeMb, maxPages }`
  - `note?: string` (present when Cloud Tasks is emulated)

Behavior:
- Uploads PDF to GCS at `uploads/{sessionId}/{jobId}.pdf`.
- Creates Firestore job doc with `status: "uploaded"` then enqueues a Cloud Task and sets `status: "queued"`.

Source: `backend/app/routers/jobs.py#create_jobs`

---

## Get job status

GET `/api/jobs/{jobId}`

- Headers: `X-Session-Id: <uuid>`
- Response body (JSON):
  - `jobId: string`
  - `status: "uploaded" | "queued" | "processing" | "extracting" | "llm" | "done" | "failed"`
  - `stages: Record<string, string>` (timestamps per stage)
  - `resultJson?: Invoice` (when done)
  - `confidenceScore?: number` (when done)
  - `error?: string` (when failed)

Source: `backend/app/routers/jobs.py#get_job_status`

---

## List jobs by session

GET `/api/sessions/{sessionId}/jobs`

- Headers: `X-Session-Id: <uuid>` must equal the path `sessionId`, else 400.
- Response body (JSON):
  - `sessionId: string`
  - `jobs: Array<{ jobId: string; filename: string; status: JobStatus; stages: Record<string, string> }>`
- Order is not guaranteed; sort client-side by desired timestamp (e.g., `stages.uploaded` or `stages.done`).

Source: `backend/app/routers/jobs.py#list_session_jobs`

---

## Retry a job

POST `/api/jobs/{jobId}/retry`

- Headers: `X-Session-Id: <uuid>`
- Status: 202 on success; returns `{ jobId, status: "queued" }`.
- 409 if original input PDF no longer exists (user should re-upload).

Source: `backend/app/routers/jobs.py#retry_job`

---

## Export session CSV

GET `/api/sessions/{sessionId}/export.csv`

- Headers: `X-Session-Id: <uuid>` must equal the path `sessionId`.
- Response: `text/csv; charset=utf-8` with header
  `Content-Disposition: attachment; filename=export-<sessionId>.csv`.
- Columns:
  - `invoiceNumber, invoiceDate, vendorName, currency, subtotal, tax, total, dueDate,
     lineItemIndex, description, quantity, unitPrice, lineTotal, confidenceScore, filename`

Source: `backend/app/routers/jobs.py#export_session_csv`

---

## Delete a session

DELETE `/api/sessions/{sessionId}`

- Headers: `X-Session-Id: <uuid>` must equal the path `sessionId`.
- Response body: `{ sessionId: string, deleted: number }`
- Deletes all jobs and attempts to delete input PDFs.

Source: `backend/app/routers/jobs.py#delete_session`

---

## Internal worker (do not call from frontend)

POST `/api/tasks/process`

- JSON body: `{ jobId: string, sessionId: string }`
- Cloud Tasks will call this endpoint with OIDC in production. When `TASKS_EMULATE=true`,
  direct calls are allowed for local testing.
- Performs OCR → LLM → validation → confidence scoring → persistence and cleans up the PDF.

Source: `backend/app/routers/tasks.py#process_task`

---

## Status values and stages

Possible `status` values:
- `uploaded` → immediately after upload
- `queued` → enqueued to process
- `processing` → lock acquired by worker
- `extracting` → OCR stage
- `llm` → LLM extraction
- `done` → success
- `failed` → terminal error

`stages` is a map of stage name to ISO timestamp (for progress and ordering).

---

## Data models (responses)

Invoice (from `backend/app/models.py`):
- `invoiceNumber: string`
- `invoiceDate: string (ISO yyyy-mm-dd)`
- `vendorName: string`
- `currency: string` (default `EUR`)
- `subtotal: number`
- `tax: number`
- `total: number`
- `dueDate?: string`
- `lineItems: InvoiceLineItem[]`
- `notes?: string | null`

InvoiceLineItem:
- `description: string`
- `quantity: number`
- `unitPrice: number`
- `lineTotal: number`

JobsCreateResponse:
- `sessionId: string`
- `jobs: Array<{ jobId: string; filename: string; status: JobStatus }>`
- `limits: { maxFiles: number; maxSizeMb: number; maxPages: number }`
- `note?: string`

---

## Recommended frontend flow

1) Generate `sessionId = crypto.randomUUID()` on first render; store per-tab.
2) GET `/api/config` to configure client-side checks (file count, size, pages, MIME).
3) Build `FormData` with PDFs and POST `/api/jobs` with `X-Session-Id`.
4) Start polling GET `/api/jobs/{jobId}` every 1–2s (with backoff) until `done` or `failed`.
5) Show a jobs list via GET `/api/sessions/{sessionId}/jobs`; sort client-side.
6) Allow retry via POST `/api/jobs/{jobId}/retry` on failures; if 409, prompt re-upload.
7) Provide Export button to GET `/api/sessions/{sessionId}/export.csv`.
8) Add "End Session" to DELETE `/api/sessions/{sessionId}` and clear local state.

---

## Minimal TypeScript types

```ts
export type UUID = string;

export type JobStatus =
  | "uploaded"
  | "queued"
  | "processing"
  | "extracting"
  | "llm"
  | "done"
  | "failed";

export interface Limits {
  maxFiles: number;
  maxSizeMb: number;
  maxPages: number;
}

export interface JobItem {
  jobId: string;
  filename: string;
  status: JobStatus;
}

export interface JobsCreateResponse {
  sessionId: UUID;
  jobs: JobItem[];
  limits: Limits;
  note?: string | null;
}

export interface InvoiceLineItem {
  description: string;
  quantity: number;
  unitPrice: number;
  lineTotal: number;
}

export interface Invoice {
  invoiceNumber: string;
  invoiceDate: string;    // ISO date
  vendorName: string;
  currency: string;       // default EUR
  subtotal: number;
  tax: number;
  total: number;
  dueDate?: string | null;
  lineItems: InvoiceLineItem[];
  notes?: string | null;
}

export interface JobDetail {
  jobId: string;
  status: JobStatus;
  stages: Record<string, string>; // timestamps
  resultJson?: Invoice;
  confidenceScore?: number;
  error?: string;
}

export interface JobsListBySession {
  sessionId: UUID;
  jobs: Array<Pick<JobDetail, "jobId" | "status"> & { filename: string; stages: Record<string, string> }>;
}
```

---

## Minimal fetch helpers (optional)

```ts
export async function upload(files: File[], sessionId: UUID, baseUrl: string) {
  const fd = new FormData();
  for (const f of files) fd.append("files", f, f.name);

  const r = await fetch(`${baseUrl}/api/jobs`, {
    method: "POST",
    headers: { "X-Session-Id": sessionId },
    body: fd,
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as JobsCreateResponse;
}

export async function getStatus(jobId: string, sessionId: UUID, baseUrl: string) {
  const r = await fetch(`${baseUrl}/api/jobs/${jobId}`, {
    headers: { "X-Session-Id": sessionId },
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as JobDetail;
}

export async function listJobs(sessionId: UUID, baseUrl: string) {
  const r = await fetch(`${baseUrl}/api/sessions/${sessionId}/jobs`, {
    headers: { "X-Session-Id": sessionId },
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as JobsListBySession;
}

export async function downloadCsv(sessionId: UUID, baseUrl: string) {
  const r = await fetch(`${baseUrl}/api/sessions/${sessionId}/export.csv`, {
    headers: { "X-Session-Id": sessionId },
  });
  if (!r.ok) throw new Error(await r.text());
  const blob = await r.blob();
  return blob;
}
```
