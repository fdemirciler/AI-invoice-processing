"""Google Cloud Vision OCR service for PDFs stored in GCS.

Uses async PDF OCR: reads PDF from GCS and writes results (JSON) to a temporary
GCS prefix, aggregates full text, then deletes the temporary outputs.

Note: Keep batch_size <= MAX_PAGES to avoid partial outputs for our limit.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Tuple

from google.cloud import storage
from google.cloud import vision_v1 as vision


@dataclass
class OcrResult:
    text: str
    pages: int


class VisionService:
    def __init__(self, bucket_name: str) -> None:
        self._storage = storage.Client()
        self._vision = vision.ImageAnnotatorClient()
        self._bucket = self._storage.bucket(bucket_name)

    def ocr_pdf_from_gcs(self, gcs_uri: str, temp_prefix: str, batch_size: int = 20) -> OcrResult:
        """Run Vision PDF OCR for a GCS PDF and return aggregated text.

        gcs_uri: gs://bucket/path/to/file.pdf
        temp_prefix: gs://bucket/tmp/output/prefix/
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

        full_text = []
        page_total = 0
        for b in blobs:
            data = b.download_as_bytes()
            resp = json.loads(data)
            for r in resp.get("responses", []):
                fta = r.get("fullTextAnnotation")
                if fta and "text" in fta:
                    full_text.append(fta["text"])
                # Increment pages even if no text to keep consistent count
                page_total += 1

        # Cleanup temporary OCR outputs
        for b in blobs:
            try:
                b.delete()
            except Exception:
                pass

        return OcrResult(text="\n".join(full_text).strip(), pages=page_total)
