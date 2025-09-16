from __future__ import annotations

"""Domain-specific exceptions for service and orchestration layers.

Routers should catch these and translate them to appropriate HTTP responses.
"""


class FileValidationError(Exception):
    """Invalid file input (mime, empty, unreadable, pages exceeded, etc.)."""


class PayloadTooLargeError(Exception):
    """Payload exceeds configured size limits (maps to HTTP 413)."""


class RateLimitError(Exception):
    """Rate limit exceeded (maps to HTTP 429)."""


class NotFoundError(Exception):
    """Resource not found or does not belong to the caller (maps to HTTP 404)."""


class ConflictError(Exception):
    """Resource conflict (e.g., missing original blob for retry) (maps to HTTP 409)."""


class LockAcquisitionError(Exception):
    """Unable to acquire processing lock (generally not an HTTP error; used internally)."""


class ExternalServiceError(Exception):
    """Upstream provider or storage error (maps to HTTP 503)."""
