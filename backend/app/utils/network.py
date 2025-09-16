from __future__ import annotations

from fastapi import Request


def get_client_ip(request: Request | None) -> str:
    """Best-effort client IP extraction (for coarse per-IP backstop).

    Prefer X-Forwarded-For (left-most) then fall back to the socket peer.
    Mirrors the previous inline implementation in routers/jobs.py.
    """
    if request is None:
        return ""
    try:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
        if request.client and request.client.host:
            return request.client.host
    except Exception:
        pass
    return ""
