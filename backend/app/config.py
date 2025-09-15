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
    LLM_PROMPT_VERSION: str

    # OCR
    OCR_LANG_HINTS: List[str]
    OCR_SYNC_MAX_PAGES: int
    OCR_PYPDF_MAX_PAGES: int
    OCR_TEXT_MIN_CHARS: int
    OCR_TEXT_KEYWORDS: str  # semicolon-separated groups of keywords; groups use '|' for synonyms

    # Retention
    RETENTION_HOURS: int
    RETENTION_LOOP_ENABLE: bool
    RETENTION_LOOP_INTERVAL_MIN: int

    # Locks
    LOCK_STALE_MINUTES: int

    # Preprocessing (sanitizer path)
    PREPROCESS_MAX_CHARS: int
    ZONE_STRIP_TOP: int
    ZONE_STRIP_BOTTOM: int

    # Rate limiting / quotas
    RL_ENABLED: bool
    RL_JOBS_PER_MIN_CAP: int
    RL_FILES_PER_MIN_CAP: int
    RL_RETRY_PER_MIN_CAP: int
    RL_DAILY_PER_SESSION: int
    RL_DAILY_GLOBAL: int
    RL_USE_IP_FALLBACK: bool
    RL_IP_PER_MIN_CAP: int
    RL_HEADER_KEY: str
    RL_TZ_OFFSET_MINUTES: int

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
        self.LLM_PROMPT_VERSION = os.getenv("LLM_PROMPT_VERSION", "v1")

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

        # Retention
        self.RETENTION_HOURS = int(os.getenv("RETENTION_HOURS", "24"))
        self.RETENTION_LOOP_ENABLE = os.getenv("RETENTION_LOOP_ENABLE", "true").lower() == "true"
        self.RETENTION_LOOP_INTERVAL_MIN = int(os.getenv("RETENTION_LOOP_INTERVAL_MIN", "60"))

        # Locks
        self.LOCK_STALE_MINUTES = int(os.getenv("LOCK_STALE_MINUTES", "15"))

        # Preprocessing (sanitizer path only)
        self.PREPROCESS_MAX_CHARS = int(os.getenv("PREPROCESS_MAX_CHARS", "20000"))
        self.ZONE_STRIP_TOP = int(os.getenv("ZONE_STRIP_TOP", "5"))
        self.ZONE_STRIP_BOTTOM = int(os.getenv("ZONE_STRIP_BOTTOM", "5"))

        # Rate limiting / quotas (defaults are conservative; override in env)
        self.RL_ENABLED = os.getenv("RL_ENABLED", "true").lower() == "true"
        self.RL_JOBS_PER_MIN_CAP = int(os.getenv("RL_JOBS_PER_MIN_CAP", "5"))
        self.RL_FILES_PER_MIN_CAP = int(os.getenv("RL_FILES_PER_MIN_CAP", "20"))
        self.RL_RETRY_PER_MIN_CAP = int(os.getenv("RL_RETRY_PER_MIN_CAP", "5"))
        self.RL_DAILY_PER_SESSION = int(os.getenv("RL_DAILY_PER_SESSION", "50"))
        self.RL_DAILY_GLOBAL = int(os.getenv("RL_DAILY_GLOBAL", "250"))
        self.RL_USE_IP_FALLBACK = os.getenv("RL_USE_IP_FALLBACK", "true").lower() == "true"
        self.RL_IP_PER_MIN_CAP = int(os.getenv("RL_IP_PER_MIN_CAP", "60"))
        self.RL_HEADER_KEY = os.getenv("RL_HEADER_KEY", "X-Session-Id")
        # CET fixed +1 minute offset (ignore DST) unless overridden
        self.RL_TZ_OFFSET_MINUTES = int(os.getenv("RL_TZ_OFFSET_MINUTES", "60"))

    @staticmethod
    def _get_list(name: str, default: str = "") -> List[str]:
        raw = os.getenv(name, default)
        return [item.strip() for item in raw.split(",") if item.strip()] or ["*"]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
