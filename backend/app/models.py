"""Pydantic models for API requests and responses."""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional
import re
from pydantic import BaseModel, Field


class Limits(BaseModel):
    """Runtime limits exposed to the frontend."""

    maxFiles: int = Field(..., description="Maximum files per request")
    maxSizeMb: int = Field(..., description="Maximum size per file in MB")
    maxPages: int = Field(..., description="Maximum pages per PDF")


class JobItem(BaseModel):
    """Basic job information returned after upload."""

    jobId: str
    filename: str
    status: str
    sizeBytes: int | None = None
    pageCount: int | None = None


class JobsCreateResponse(BaseModel):
    """Response for creating upload jobs."""

    sessionId: str
    jobs: List[JobItem]
    limits: Limits
    note: Optional[str] = None


class InvoiceLineItem(BaseModel):
    """A single invoice line item."""

    description: str
    quantity: float = Field(ge=0)
    unitPrice: float = Field(ge=0)
    lineTotal: float = Field(ge=0)


class Invoice(BaseModel):
    """Structured invoice data returned by the pipeline."""

    invoiceNumber: str
    invoiceDate: date
    vendorName: str
    currency: str = Field(default="EUR")
    subtotal: float = Field(ge=0)
    tax: float = Field(ge=0)
    total: float = Field(ge=0)
    dueDate: Optional[date] = None
    lineItems: List[InvoiceLineItem]
    notes: Optional[str] = None

    @staticmethod
    def _parse_date(value: str | date) -> date:
        if isinstance(value, date):
            return value
        # Try EU first, then ISO
        for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y"):
            try:
                return datetime.strptime(value.strip(), fmt).date()
            except Exception:
                continue
        # Pydantic will handle fallback if this raises
        raise ValueError("Unrecognized date format; use dd-mm-yyyy or yyyy-mm-dd")

    @classmethod
    def model_validate_jsonish(cls, data: dict) -> "Invoice":
        # Normalize dates if provided as strings
        if isinstance(data.get("invoiceDate"), str):
            data["invoiceDate"] = cls._parse_date(data["invoiceDate"])  # type: ignore[assignment]
        if isinstance(data.get("dueDate"), str):
            try:
                data["dueDate"] = cls._parse_date(data["dueDate"])  # type: ignore[assignment]
            except Exception:
                data["dueDate"] = None
        # Coerce currency
        cur = (data.get("currency") or "EUR").upper()
        data["currency"] = cur
        
        def _parse_number(val) -> float:
            """Parse numbers from mixed-locale strings.

            Accepts strings like "€ 1.234,56", "1,234.56", "1234.56", "2x", "2 pcs".
            Strategy:
            - Strip currency symbols and letters, keep digits, separators (., ,), minus, and parentheses.
            - Detect decimal separator by the rightmost of ',' or '.'. Treat the other as thousand sep and remove.
            - Support negatives in parentheses, e.g., (123.45) -> -123.45.
            """
            if val is None:
                raise ValueError("empty number")
            if isinstance(val, (int, float)):
                return float(val)
            s = str(val).strip()
            if not s:
                raise ValueError("empty number")
            # Parentheses negative
            neg = False
            if s.startswith("(") and s.endswith(")"):
                neg = True
                s = s[1:-1]
            # Remove all but digits, separators, minus
            s = re.sub(r"[^0-9,\.\-]", "", s)
            # If both separators appear, choose rightmost as decimal
            last_comma = s.rfind(',')
            last_dot = s.rfind('.')
            if last_comma == -1 and last_dot == -1:
                num = float(s or 0)
            else:
                if last_comma > last_dot:
                    # comma decimal; remove all dots (thousands), replace comma with dot
                    num = float(s.replace('.', '').replace(',', '.'))
                else:
                    # dot decimal; remove all commas (thousands)
                    num = float(s.replace(',', ''))
            if neg:
                num = -num
            return num

        # Ensure numeric fields are floats (tolerant parsing)
        for k in ("subtotal", "tax", "total"):
            if k in data:
                try:
                    data[k] = _parse_number(data[k])
                except Exception:
                    pass  # let model validation surface errors if still invalid

        # Sanitize line items: parse numbers, infer missing lineTotal, drop invalid/negative items
        raw_items = data.get("lineItems") or []
        clean_items: List[dict] = []
        for it in raw_items:
            # Require description
            desc = (it.get("description") or "").strip()
            if not desc:
                continue
            try:
                q = _parse_number(it.get("quantity")) if it.get("quantity") is not None else None
                up = _parse_number(it.get("unitPrice")) if it.get("unitPrice") is not None else None
                lt = _parse_number(it.get("lineTotal")) if it.get("lineTotal") is not None else None
            except Exception:
                # Skip items that cannot be parsed
                continue
            # Infer missing lineTotal
            if lt is None and q is not None and up is not None:
                lt = q * up
            # Validate non-negative and presence
            try:
                if q is None or up is None or lt is None:
                    continue
                if q < 0 or up < 0 or lt < 0:
                    continue
                clean_items.append({
                    "description": desc,
                    "quantity": float(q),
                    "unitPrice": float(up),
                    "lineTotal": float(lt),
                })
            except Exception:
                continue
        data["lineItems"] = clean_items

        return cls.model_validate(data)

    def to_csv_rows(self, filename: str, confidence: float | None = None) -> List[dict]:
        rows: List[dict] = []
        for idx, li in enumerate(self.lineItems, start=1):
            rows.append(
                {
                    "invoiceNumber": self.invoiceNumber,
                    "invoiceDate": self.invoiceDate.isoformat(),
                    "vendorName": self.vendorName,
                    "currency": self.currency,
                    "subtotal": self.subtotal,
                    "tax": self.tax,
                    "total": self.total,
                    "dueDate": self.dueDate.isoformat() if self.dueDate else "",
                    "lineItemIndex": idx,
                    "description": li.description,
                    "quantity": li.quantity,
                    "unitPrice": li.unitPrice,
                    "lineTotal": li.lineTotal,
                    "confidenceScore": confidence if confidence is not None else "",
                    "filename": filename,
                }
            )
        return rows
