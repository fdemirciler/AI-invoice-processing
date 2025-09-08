"""Google Cloud Vision OCR service for PDFs stored in GCS.

Tiered strategy:
- Try PyPDF text-layer extraction first (fast, free). If text quality is sufficient, skip OCR.
- Use synchronous Vision for short scans (low overhead for small PDFs).
- Fall back to asynchronous Vision for longer scans (robust for many pages).

Note: Keep batch_size <= MAX_PAGES to avoid partial outputs for our limit.
"""
from __future__ import annotations

import io
import json
import time
from dataclasses import dataclass, field
from typing import Tuple, List

from google.cloud import storage
from google.cloud import vision_v1 as vision
from pypdf import PdfReader

from ..config import get_settings


@dataclass
class OcrResult:
    text: str
    pages: int
    method: str = "vision_async"
    page_texts: List[str] = field(default_factory=list)


class VisionService:
    def __init__(self, bucket_name: str) -> None:
        self._storage = storage.Client()
        self._vision = vision.ImageAnnotatorClient()
        self._bucket = self._storage.bucket(bucket_name)

    # Public API (keeps original name). Added optional page_count for tiering.
    def ocr_pdf_from_gcs(
        self, gcs_uri: str, temp_prefix: str, batch_size: int = 20, page_count: int | None = None
    ) -> OcrResult:
        """Tiered OCR for a GCS PDF and return aggregated text.

        gcs_uri: gs://bucket/path/to/file.pdf
        temp_prefix: gs://bucket/tmp/output/prefix/
        """
        settings = get_settings()

        # If we don't know page count, fall back to async (robust for any size)
        if page_count is None:
            return self._ocr_async(gcs_uri, temp_prefix, batch_size=batch_size)

        # 1) Try PyPDF text layer for small-ish PDFs
        if page_count <= settings.OCR_PYPDF_MAX_PAGES:
            try:
                pypdf_res = self._try_extract_text_layer(gcs_uri, page_count)
                if self._is_text_quality_sufficient(pypdf_res.text):
                    pypdf_res.method = "pypdf"
                    return pypdf_res
            except Exception:
                # Ignore and continue to OCR paths
                pass

        # 2) Use synchronous Vision OCR for short scans
        if page_count <= settings.OCR_SYNC_MAX_PAGES:
            return self._ocr_sync(gcs_uri, page_count)

        # 3) Fall back to async for longer scans
        return self._ocr_async(gcs_uri, temp_prefix, batch_size=batch_size)

    # --- Helpers ---
    def _try_extract_text_layer(self, gcs_uri: str, page_count: int) -> OcrResult:
        """Extract text layer with PyPDF if present (downloads the PDF)."""
        blob_path = gcs_uri.replace(f"gs://{self._bucket.name}/", "")
        blob = self._bucket.blob(blob_path)
        pdf_bytes = blob.download_as_bytes()

        reader = PdfReader(io.BytesIO(pdf_bytes))
        full_text: List[str] = []
        for page in reader.pages:
            try:
                full_text.append(page.extract_text() or "")
            except Exception:
                full_text.append("")

        return OcrResult(text="\n".join(full_text).strip(), pages=page_count, method="pypdf", page_texts=full_text)

    def _parse_keyword_groups(self) -> List[List[str]]:
        settings = get_settings()
        raw = settings.OCR_TEXT_KEYWORDS.strip()
        groups: List[List[str]] = []
        if not raw:
            return groups
        for grp in raw.split(";"):
            tokens = [t.strip().lower() for t in grp.split("|") if t.strip()]
            if tokens:
                groups.append(tokens)
        return groups

    def _is_text_quality_sufficient(self, text: str) -> bool:
        """
        Performs a more robust quality check on extracted text.
        Checks for minimum length, keywords, and now structural integrity patterns.
        """
        if not text or len(text) < 200:
            return False

        # --- Keyword Check (existing logic) ---
        required_keywords = ["invoice", "total", "factuur", "totaal"]
        text_lower = text.lower()
        if not any(keyword in text_lower for keyword in required_keywords):
            if not any(symbol in text for symbol in ["€", "$", "£"]):
                return False

        # --- Character Ratio Check (existing logic) ---
        alpha_chars = 0
        non_alpha_numeric_chars = 0
        for char in text:
            if char.isalpha():
                alpha_chars += 1
            elif not char.isspace() and not char.isnumeric():
                non_alpha_numeric_chars += 1
        
        if alpha_chars == 0:
            return False

        badness_ratio = non_alpha_numeric_chars / alpha_chars
        if badness_ratio > 0.3:
            return False

        # --- NEW: Structural Pattern Check for CSV-like lines ---
        # Heuristic: If many lines look like CSV data, the text layer is likely bad.
        lines = text.splitlines()
        # To keep this check fast, we only sample the first 50 lines.
        sample_lines = lines[:50]
        csv_like_line_count = 0
        for line in sample_lines:
            # Check for lines that start with a quote and contain a comma
            # which is a strong signal of a poorly extracted text layer.
            if line.strip().startswith('"') and "," in line:
                csv_like_line_count += 1
        
        # If more than 20% of the sampled lines look like CSV, fail the check.
        if len(sample_lines) > 0 and (csv_like_line_count / len(sample_lines)) > 0.2:
            return False

        return True

    def _ocr_sync(self, gcs_uri: str, page_count: int) -> OcrResult:
        """Synchronous Vision OCR for small PDFs (returns result directly)."""
        feature = vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)
        gcs_source = vision.GcsSource(uri=gcs_uri)
        input_config = vision.InputConfig(gcs_source=gcs_source, mime_type="application/pdf")
        request = vision.AnnotateFileRequest(
            input_config=input_config, features=[feature], pages=list(range(1, page_count + 1))
        )
        response = self._vision.batch_annotate_files(requests=[request])

        full_text: List[str] = []
        page_texts: List[str] = []
        pages = 0
        for file_resp in response.responses:
            for img_resp in getattr(file_resp, "responses", []) or []:
                fta = getattr(img_resp, "full_text_annotation", None)
                if fta and getattr(fta, "text", None):
                    full_text.append(fta.text)
                    page_texts.append(fta.text)
                else:
                    page_texts.append("")
                pages += 1

        return OcrResult(text="\n".join(full_text).strip(), pages=pages or page_count, method="vision_sync", page_texts=page_texts)

    def _ocr_async(self, gcs_uri: str, temp_prefix: str, batch_size: int = 20) -> OcrResult:
        """Asynchronous Vision OCR for larger PDFs (writes outputs to GCS, then aggregates)."""
        input_config = vision.InputConfig(
            gcs_source=vision.GcsSource(uri=gcs_uri), mime_type="application/pdf"
        )
        output_config = vision.OutputConfig(
            gcs_destination=vision.GcsDestination(uri=temp_prefix), batch_size=batch_size
        )
        feature = vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)
        request = vision.AsyncAnnotateFileRequest(
            features=[feature], input_config=input_config, output_config=output_config
        )

        operation = self._vision.async_batch_annotate_files(requests=[request])
        operation.result(timeout=300)

        # List output JSON files in the temp prefix
        prefix_path = temp_prefix.replace(f"gs://{self._bucket.name}/", "")
        blobs = list(self._storage.list_blobs(self._bucket.name, prefix=prefix_path))

        full_text: List[str] = []
        page_texts: List[str] = []
        page_total = 0
        for b in blobs:
            data = b.download_as_bytes()
            resp = json.loads(data)
            for r in resp.get("responses", []):
                fta = r.get("fullTextAnnotation")
                if fta and "text" in fta:
                    full_text.append(fta["text"])
                    page_texts.append(fta["text"]) 
                else:
                    page_texts.append("")
                page_total += 1

        # Cleanup temporary OCR outputs
        for b in blobs:
            try:
                b.delete()
            except Exception:
                pass

        return OcrResult(text="\n".join(full_text).strip(), pages=page_total, method="vision_async", page_texts=page_texts)
