from __future__ import annotations

from ..models import Invoice


def compute_confidence(ocr_text: str, pages: int, inv: Invoice) -> float:
    """Compute a confidence score based on OCR quality, validity, consistency, and coverage.

    Mirrors the prior _compute_confidence implementation in routers/tasks.py.
    """
    # OCR quality: chars per page heuristic
    pages = max(1, pages)
    ocr_quality = min(1.0, len(ocr_text) / float(pages * 800))

    # LLM validity: if we have a validated Invoice, assume high
    llm_validity = 1.0

    # Consistency: subtotal + tax ~ total; sum(lineTotals) ~ subtotal
    def closeness(expected: float, actual: float) -> float:
        if expected <= 0:
            return 0.0
        return max(0.0, 1.0 - min(abs(actual - expected) / expected, 1.0))

    sum_lines = sum(li.lineTotal for li in inv.lineItems) if inv.lineItems else 0.0
    c1 = closeness(inv.subtotal + inv.tax, inv.total)
    c2 = closeness(inv.subtotal, sum_lines)
    consistency = (c1 + c2) / 2.0

    # Coverage: how many key fields present
    fields_present = 0
    total_fields = 8
    fields_present += 1 if inv.invoiceNumber else 0
    fields_present += 1 if inv.invoiceDate else 0
    fields_present += 1 if inv.vendorName else 0
    fields_present += 1 if inv.currency else 0
    fields_present += 1 if inv.subtotal is not None else 0
    fields_present += 1 if inv.tax is not None else 0
    fields_present += 1 if inv.total is not None else 0
    fields_present += 1 if inv.lineItems else 0
    coverage = fields_present / float(total_fields)

    score = 0.4 * ocr_quality + 0.3 * llm_validity + 0.2 * consistency + 0.1 * coverage
    return round(score, 3)
