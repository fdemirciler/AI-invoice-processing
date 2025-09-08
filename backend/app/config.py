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
    OCR_SYNC_MAX_PAGES: int
    OCR_PYPDF_MAX_PAGES: int
    OCR_TEXT_MIN_CHARS: int
    OCR_TEXT_KEYWORDS: str  # semicolon-separated groups of keywords; groups use '|' for synonyms
    # Preprocessor (page/line filtering)
    PREPROC_MIN_PAGES_TO_FILTER: int
    PREPROC_PAGE_KEYWORDS: str
    PREPROC_LINE_KEYWORDS: str
    PREPROC_DATE_REGEX: str
    PREPROC_AMOUNT_REGEX: str
    PREPROC_MAX_CHARS: int

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
        self.OCR_SYNC_MAX_PAGES = int(os.getenv("OCR_SYNC_MAX_PAGES", "2"))
        self.OCR_PYPDF_MAX_PAGES = int(os.getenv("OCR_PYPDF_MAX_PAGES", "10"))
        self.OCR_TEXT_MIN_CHARS = int(os.getenv("OCR_TEXT_MIN_CHARS", "200"))
        # groups: 'invoice|factuur' and 'total|totaal|bedrag|omschrijving|prijs'
        self.OCR_TEXT_KEYWORDS = os.getenv(
            "OCR_TEXT_KEYWORDS",
            "invoice|factuur;total|totaal|bedrag|omschrijving|prijs",
        )

        # Preprocessor (page/line filtering)
        self.PREPROC_MIN_PAGES_TO_FILTER = int(os.getenv("PREPROC_MIN_PAGES_TO_FILTER", "3"))
        self.PREPROC_PAGE_KEYWORDS = os.getenv(
            "PREPROC_PAGE_KEYWORDS",
            r"invoice|factuur|total|totaal|vat|amount|bedrag|omschrijving|prijs|€|\$|£",
        )
        self.PREPROC_LINE_KEYWORDS = os.getenv(
            "PREPROC_LINE_KEYWORDS",
            r"invoice|factuur|total|totaal|vat|amount|bedrag|eur|usd|\$|£|item|date|omschrijving|prijs",
        )
        self.PREPROC_DATE_REGEX = os.getenv("PREPROC_DATE_REGEX", r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b")
        self.PREPROC_AMOUNT_REGEX = os.getenv("PREPROC_AMOUNT_REGEX", r"\b\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})\b")
        self.PREPROC_MAX_CHARS = int(os.getenv("PREPROC_MAX_CHARS", "20000"))

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
