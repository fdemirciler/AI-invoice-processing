"""FastAPI dependencies (e.g., session header parsing)."""
from __future__ import annotations

import re
from fastapi import Header, HTTPException

_SESSION_RE = re.compile(r"^[0-9a-fA-F-]{36}$")


def get_session_id(x_session_id: str | None = Header(default=None, alias="X-Session-Id")) -> str:
    """Validate and return the session ID from the `X-Session-Id` header.

    The frontend should generate a UUID v4 per page load and send it with every request.
    We accept any 36-char UUID pattern and treat missing/invalid as 400.
    """
    if not x_session_id or not _SESSION_RE.match(x_session_id):
        raise HTTPException(status_code=400, detail="Missing or invalid X-Session-Id header")
    return x_session_id
