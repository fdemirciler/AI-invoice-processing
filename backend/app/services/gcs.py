"""Google Cloud Storage helper service."""
from __future__ import annotations

from typing import Optional
from google.cloud import storage


class GCSService:
    """Wrapper around google-cloud-storage for simple operations."""

    def __init__(self, bucket_name: str) -> None:
        self.bucket_name = bucket_name
        self._client = storage.Client()
        self._bucket = self._client.bucket(bucket_name)

    def upload_bytes(self, blob_path: str, data: bytes, content_type: str = "application/pdf") -> str:
        blob = self._bucket.blob(blob_path)
        blob.upload_from_string(data, content_type=content_type)
        return f"gs://{self.bucket_name}/{blob_path}"

    def delete_blob(self, blob_path: str) -> None:
        blob = self._bucket.blob(blob_path)
        blob.delete(if_generation_match=None)  # ignore preconditions

    def blob_exists(self, blob_path: str) -> bool:
        blob = self._bucket.blob(blob_path)
        return blob.exists()
