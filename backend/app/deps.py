"""FastAPI dependencies (e.g., session header parsing)."""
from __future__ import annotations

import re
from fastapi import Header, HTTPException
from typing import Annotated
from google.oauth2 import id_token
from google.auth.transport.requests import Request
from .config import get_settings

_SESSION_RE = re.compile(r"^[0-9a-fA-F-]{36}$")


def get_session_id(x_session_id: str | None = Header(default=None, alias="X-Session-Id")) -> str:
    """Validate and return the session ID from the `X-Session-Id` header.

    The frontend should generate a UUID v4 per page load and send it with every request.
    We accept any 36-char UUID pattern and treat missing/invalid as 400.
    """
    if not x_session_id or not _SESSION_RE.match(x_session_id):
        raise HTTPException(status_code=400, detail="Missing or invalid X-Session-Id header")
    return x_session_id


async def verify_oidc_token(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> dict:
    """Verify Google-issued OIDC token for Cloud Tasks worker invocations.

    Behavior:
    - When TASKS_EMULATE is true (local/dev), bypass verification.
    - Otherwise, require an Authorization: Bearer <token> header.
    - Verify signature, expiry, and audience against TASKS_TARGET_URL.
    - Enforce the caller's email equals TASKS_SERVICE_ACCOUNT_EMAIL.
    """
    settings = get_settings()

    # Bypass in emulation mode to simplify local development
    if settings.TASKS_EMULATE:
        return {"email": "emulated-task@example.com"}

    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    try:
        token_type, token = authorization.split(" ", 1)
        if token_type.lower() != "bearer" or not token:
            raise ValueError("Invalid token type")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Authorization header format")

    try:
        decoded = id_token.verify_oauth2_token(
            token,
            Request(),
            settings.TASKS_TARGET_URL,
        )

        caller = decoded.get("email")
        if not caller or caller != settings.TASKS_SERVICE_ACCOUNT_EMAIL:
            raise HTTPException(status_code=403, detail="Token is from an unauthorized service account")

        return decoded
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=401, detail=f"Invalid OIDC token: {exc}")
