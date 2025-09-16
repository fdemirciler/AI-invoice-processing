from __future__ import annotations

import io
from fastapi import HTTPException
from pypdf import PdfReader


def count_pdf_pages(data: bytes) -> int:
    """Count pages of a PDF from raw bytes.

    Raises HTTP 400 (Bad Request) on invalid or unreadable PDFs to match previous behavior.
    """
    try:
        reader = PdfReader(io.BytesIO(data))
        return len(reader.pages)
    except Exception as exc:  # noqa: BLE001 broad, returns user error
        raise HTTPException(status_code=400, detail="Invalid or unreadable PDF") from exc
