"""Application settings and configuration helpers."""
from __future__ import annotations

import os
from functools import lru_cache
from typing import List
from dotenv import load_dotenv, find_dotenv


class Settings:
    """Runtime configuration loaded from environment variables.

    Defaults are suitable for local development. Production should set
    explicit values via environment variables and Secret Manager.
    """

    APP_NAME: str = "Invoice Processing API"
    API_PREFIX: str = "/api"

    # CORS
    CORS_ORIGINS: List[str]

    # Limits
    MAX_FILES: int
    MAX_SIZE_MB: int
    MAX_PAGES: int
    ACCEPTED_MIME: List[str]

    # GCP
    GCS_BUCKET: str
    REGION: str
    FIRESTORE_DATABASE_ID: str

    # Cloud Tasks
    GCP_PROJECT: str
    TASKS_QUEUE: str
    TASKS_TARGET_URL: str
    TASKS_SERVICE_ACCOUNT_EMAIL: str
    TASKS_EMULATE: bool

    # LLM
    GEMINI_API_KEY: str
    GEMINI_MODEL: str
    OPENROUTER_API_KEY: str
    OPENROUTER_MODEL: str

    # OCR
    OCR_LANG_HINTS: List[str]

    # Retention
    RETENTION_HOURS: int
    RETENTION_LOOP_ENABLE: bool
    RETENTION_LOOP_INTERVAL_MIN: int

    # Locks
    LOCK_STALE_MINUTES: int

    def __init__(self) -> None:
        # Load .env once (supports parent directories)
        load_dotenv(find_dotenv(), override=False)
        self.CORS_ORIGINS = self._get_list("CORS_ORIGINS", default="*")
        self.MAX_FILES = int(os.getenv("MAX_FILES", "10"))
        self.MAX_SIZE_MB = int(os.getenv("MAX_SIZE_MB", "10"))
        self.MAX_PAGES = int(os.getenv("MAX_PAGES", "20"))
        self.ACCEPTED_MIME = ["application/pdf"]

        self.GCS_BUCKET = os.getenv("GCS_BUCKET", "invoice_processing_storage")
        self.REGION = os.getenv("REGION", "europe-west4")
        self.FIRESTORE_DATABASE_ID = os.getenv("FIRESTORE_DATABASE_ID", "(default)")

        # Cloud Tasks / GCP project configuration
        self.GCP_PROJECT = os.getenv("GCP_PROJECT", os.getenv("GOOGLE_CLOUD_PROJECT", ""))
        self.TASKS_QUEUE = os.getenv("TASKS_QUEUE", "invoice-process-queue")
        self.TASKS_TARGET_URL = os.getenv("TASKS_TARGET_URL", "")  # e.g., https://<run-url>/api/tasks/process
        self.TASKS_SERVICE_ACCOUNT_EMAIL = os.getenv("TASKS_SERVICE_ACCOUNT_EMAIL", "")
        self.TASKS_EMULATE = os.getenv("TASKS_EMULATE", "true").lower() == "true"

        # LLM
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
        self.GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
        self.OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")

        # OCR
        self.OCR_LANG_HINTS = self._get_list("OCR_LANG_HINTS", default="en,nl")

        # Retention
        self.RETENTION_HOURS = int(os.getenv("RETENTION_HOURS", "24"))
        self.RETENTION_LOOP_ENABLE = os.getenv("RETENTION_LOOP_ENABLE", "true").lower() == "true"
        self.RETENTION_LOOP_INTERVAL_MIN = int(os.getenv("RETENTION_LOOP_INTERVAL_MIN", "60"))

        # Locks
        self.LOCK_STALE_MINUTES = int(os.getenv("LOCK_STALE_MINUTES", "15"))

    @staticmethod
    def _get_list(name: str, default: str = "") -> List[str]:
        raw = os.getenv(name, default)
        return [item.strip() for item in raw.split(",") if item.strip()] or ["*"]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
