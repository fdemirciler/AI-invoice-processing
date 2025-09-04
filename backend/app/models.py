"""Pydantic models for API requests and responses."""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional
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
        # Ensure numeric fields are floats
        for k in ("subtotal", "tax", "total"):
            if k in data and isinstance(data[k], str):
                data[k] = float(data[k].replace(",", "."))
        # Line totals safety
        items = data.get("lineItems") or []
        for it in items:
            for k in ("quantity", "unitPrice", "lineTotal"):
                if k in it and isinstance(it[k], str):
                    it[k] = float(it[k].replace(",", "."))
            if not it.get("lineTotal") and it.get("quantity") is not None and it.get("unitPrice") is not None:
                it["lineTotal"] = float(it["quantity"]) * float(it["unitPrice"])  # type: ignore[arg-type]
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
