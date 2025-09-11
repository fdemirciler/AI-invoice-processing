"""Google Cloud Vision OCR service for PDFs stored in GCS.

Strategy:
- Use synchronous Vision for short scans (low overhead for small PDFs).
- Fall back to asynchronous Vision for longer scans (robust for many pages).

Optionally returns raw annotations for preprocessing.

Note: Keep batch_size <= MAX_PAGES to avoid partial outputs for our limit.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import List, Optional

from google.cloud import storage
from google.cloud import vision_v1 as vision
from google.protobuf.json_format import MessageToDict

from ..config import get_settings


@dataclass
class OcrResult:
    text: str
    pages: int
    method: str = "vision_async"
    annotations: Optional[List[dict]] = None


class VisionService:
    def __init__(self, bucket_name: str) -> None:
        self._storage = storage.Client()
        self._vision = vision.ImageAnnotatorClient()
        self._bucket = self._storage.bucket(bucket_name)

    # Public API (keeps original name). Added optional page_count and return_annotations.
    def ocr_pdf_from_gcs(
        self,
        gcs_uri: str,
        temp_prefix: str,
        batch_size: int = 20,
        page_count: int | None = None,
        return_annotations: bool = False,
    ) -> OcrResult:
        """Tiered OCR for a GCS PDF and return aggregated text.

        gcs_uri: gs://bucket/path/to/file.pdf
        temp_prefix: gs://bucket/tmp/output/prefix/
        """
        settings = get_settings()

        # If we don't know page count, fall back to async (robust for any size)
        if page_count is None:
            return self._ocr_async(gcs_uri, temp_prefix, batch_size=batch_size, return_annotations=return_annotations)

        # 1) PyPDF text layer is removed due to unsatisfactory results

        # 2) Use synchronous Vision OCR for short scans
        if page_count <= settings.OCR_SYNC_MAX_PAGES:
            return self._ocr_sync(gcs_uri, page_count, return_annotations=return_annotations)

        # 3) Fall back to async for longer scans
        return self._ocr_async(
            gcs_uri, temp_prefix, batch_size=batch_size, return_annotations=return_annotations
        )

    
    # --- extractors ---

    def _ocr_sync(self, gcs_uri: str, page_count: int, *, return_annotations: bool = False) -> OcrResult:
        """Synchronous Vision OCR for small PDFs (returns result directly).

        When return_annotations is True, also returns Vision responses as dicts for preprocessing.
        """
        feature = vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)
        gcs_source = vision.GcsSource(uri=gcs_uri)
        input_config = vision.InputConfig(gcs_source=gcs_source, mime_type="application/pdf")
        request = vision.AnnotateFileRequest(
            input_config=input_config, features=[feature], pages=list(range(1, page_count + 1))
        )
        response = self._vision.batch_annotate_files(requests=[request])

        full_text: List[str] = []
        pages = 0
        annotations: List[dict] = [] if return_annotations else None  # type: ignore[assignment]
        for file_resp in response.responses:
            for img_resp in getattr(file_resp, "responses", []) or []:
                fta = getattr(img_resp, "full_text_annotation", None)
                if fta and getattr(fta, "text", None):
                    full_text.append(fta.text)
                pages += 1
                if return_annotations:
                    try:
                        msg = getattr(img_resp, "_pb", img_resp)
                        annotations.append(MessageToDict(msg))  # type: ignore[arg-type]
                    except Exception:
                        pass
        return OcrResult(
            text="\n".join(full_text).strip(),
            pages=pages or page_count,
            method="vision_sync",
            annotations=annotations,
        )

    def _ocr_async(self, gcs_uri: str, temp_prefix: str, batch_size: int = 20, *, return_annotations: bool = False) -> OcrResult:
        """Asynchronous Vision OCR for larger PDFs (writes outputs to GCS, then aggregates).

        When return_annotations is True, also returns per-page Vision responses as dicts.
        """
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
        annotations: List[dict] = [] if return_annotations else None  # type: ignore[assignment]
        page_total = 0
        for b in blobs:
            data = b.download_as_bytes()
            resp = json.loads(data)
            for r in resp.get("responses", []):
                fta = r.get("fullTextAnnotation")
                if fta and "text" in fta:
                    full_text.append(fta["text"])
                page_total += 1
                if return_annotations and annotations is not None:
                    annotations.append(r)

        # Cleanup temporary OCR outputs
        for b in blobs:
            try:
                b.delete()
            except Exception:
                pass

        return OcrResult(
            text="\n".join(full_text).strip(),
            pages=page_total,
            method="vision_async",
            annotations=annotations,
        )
