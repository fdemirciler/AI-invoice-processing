# Backend Architecture

This document describes the refactored backend architecture of the Invoice Processing API. The goals are:
- Keep routers thin and focused on HTTP concerns.
- Centralize business orchestration in explicit services.
- Extract small, pure helpers for the pipeline steps.
- Preserve current behavior and API shapes for the frontend.

## Overview

- Routers (`backend/app/routers/`)
  - `jobs.py`: HTTP endpoints for uploads, listing, retry, export, and session delete. Thin — delegates to orchestration.
  - `tasks.py`: Worker HTTP endpoint that triggers processing. Thin — delegates to orchestration.

- Orchestration services (`backend/app/services/orchestration/`)
  - `job_service.py` (`JobOrchestrationService`):
    - `create_upload_jobs(session_id, files, client_ip=None)`
    - `retry_job(job_id, session_id)`
    - `get_session_jobs_as_csv(session_id)`
    - `delete_session_data(session_id)`
  - `task_pipeline.py` (`TaskPipelineService`):
    - `process_invoice_job(job_id, session_id)` — orchestrates OCR → sanitize → LLM → validate → score → persist → cleanup

- Pipeline modules (`backend/app/pipeline/`)
  - `preprocessing.py`: `sanitize_for_llm(text, max_chars, strip_top, strip_bottom)`
  - `evaluation.py`: `compute_confidence(ocr_text, pages, invoice)`

- Core services (`backend/app/services/`)
  - `llm.py` (Gemini primary, OpenRouter fallback; async httpx)
  - `vision.py` (OCR: sync for short scans, async for longer)
  - `firestore.py` (CRUD, locking, queries, retention)
  - `gcs.py` (upload, exists, delete)
  - `tasks.py` (Cloud Tasks enqueue helper)
  - `rate_limit.py` (token buckets + daily counters in Firestore)

- Utilities (`backend/app/utils/`)
  - `network.py` — `get_client_ip(request)`
  - `pdf.py` — `count_pdf_pages(bytes)`

- Models and config
  - `models.py` — Pydantic models and tolerant `Invoice.model_validate_jsonish()`
  - `config.py` — simple Settings loader (env-based)

## Request lifecycles

- Upload (POST `/api/jobs`)
  1. Router extracts session ID and client IP.
  2. Delegates to `JobOrchestrationService.create_upload_jobs()`.
  3. Service validates inputs, enforces rate limits, uploads to GCS, creates Firestore docs, enqueues Cloud Task, sets `queued`.
  4. If `TASKS_EMULATE=true`, it schedules the pipeline directly with `TaskPipelineService`.

- Retry (POST `/api/jobs/{jobId}/retry`)
  1. Router delegates to `JobOrchestrationService.retry_job()`.
  2. Service validates job ownership, checks GCS PDF existence, enqueues, sets `queued`, increments `manualRetries`.
  3. Emulation path uses `TaskPipelineService` directly.

- Worker processing (POST `/api/tasks/process`)
  1. Router validates payload and calls `TaskPipelineService.process_invoice_job()`.
  2. Pipeline acquires lock → OCR → sanitizer → LLM → validate → confidence → persist → cleanup → release lock.
  3. Status transitions: `processing` (via lock) → `extracting` → `llm` → `done` / `failed` (with `error`). Heartbeats are written between stages.

- Export CSV (GET `/api/sessions/{sessionId}/export.csv`)
  - Router delegates to `JobOrchestrationService.get_session_jobs_as_csv()` which fetches "done" jobs and renders CSV rows using `Invoice.to_csv_rows()`.

- Delete session (DELETE `/api/sessions/{sessionId}`)
  - Router delegates to `JobOrchestrationService.delete_session_data()` which removes GCS blobs (best-effort) and deletes job docs.

## Status and stage semantics

- Stages used by the frontend to show progress (see `frontend/src/lib/jobStages.ts`):
  - `uploaded` → `queued` → `processing` → `extracting` → `llm` → `done` (or `failed`).
- Heartbeats are written periodically to help observe activity during long stages.

## Error handling (domain exceptions)

- Domain exceptions live in `backend/app/exceptions.py`:
  - `FileValidationError`, `PayloadTooLargeError`, `RateLimitError`, `NotFoundError`, `ConflictError`, `LockAcquisitionError`, `ExternalServiceError`.
- Orchestration services raise these exceptions to signal specific failure modes.
- Routers should translate them to HTTP responses:
  - 400 → `FileValidationError`
  - 413 → `PayloadTooLargeError`
  - 404 → `NotFoundError`
  - 409 → `ConflictError`
  - 429 → `RateLimitError`
  - 503 → `ExternalServiceError`
- Note: The rate limiter (`RateLimiterService.enforce_*`) already returns rich `HTTPException` with headers; we do not wrap it to avoid losing headers.

## Configuration

- Settings (`backend/app/config.py`)
  - Key envs: `MAX_FILES`, `MAX_SIZE_MB`, `MAX_PAGES`, `GCS_BUCKET`, Cloud Tasks config, OCR and sanitizer limits, retention, rate limits.
  - `TASKS_EMULATE=true` will bypass Cloud Tasks and invoke the pipeline service directly on the same process for local development.
- Retention
  - Background loop lives in `backend/app/main.py` (toggle via env).
  - Optional future: expose a protected `/admin/retention/run` endpoint for Cloud Scheduler.

## Logging

- All services use `logging.getLogger(__name__)` and log key events:
  - Job creation / enqueue failures
  - OCR method used
  - Sanitization metrics
  - Errors per stage

## Extending the pipeline

- Add or reorder steps in `TaskPipelineService` (e.g., extra validation or formatting) while keeping routers unchanged.
- Extract new step helpers into `backend/app/pipeline/` as pure functions to improve testability.

## Developer notes

- API compatibility: The refactor aims to preserve API shapes and frontend behavior.
- Emulation mode: With `TASKS_EMULATE=true`, uploads immediately schedule processing in the same process via `TaskPipelineService`.
- Rate limiting: 429 responses provide `Retry-After` and `X-RateLimit-*` headers.
