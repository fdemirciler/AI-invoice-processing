"""LLM service: Gemini primary, OpenRouter fallback, returning strict JSON.

Async implementation using httpx so the FastAPI event loop is not blocked
while waiting on upstream LLM APIs. Includes lightweight retries via tenacity
for transient network and 429/5xx responses.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional
import os

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
)

from ..config import get_settings

logger = logging.getLogger(__name__)


# Retry predicate: network errors, timeouts, and 429/5xx HTTP errors
def _is_retryable(exc: Exception) -> bool:  # pragma: no cover - simple predicate
    if isinstance(exc, (httpx.RequestError, httpx.TimeoutException)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status == 429 or 500 <= status < 600
    return False

JSON_INSTRUCTIONS = (
    "You are an expert invoice extraction engine. Input text is OCR of an invoice and may be English or Dutch (Nederlands). "
    "It may be PREPROCESSED and contain a summary marker like '...[N line items summarized]...'. "
    "Extract a single strict JSON object with keys: "
    "invoiceNumber (string), invoiceDate (YYYY-MM-DD), vendorName (string), currency (3-letter ISO), "
    "subtotal (number), tax (number), total (number), dueDate (YYYY-MM-DD or null), "
    "lineItems (array of {description, quantity, unitPrice, lineTotal}), notes (optional). "
    "Rules: "
    "- If the summary marker '...[N line items summarized]...' is present, DO NOT attempt to reconstruct items; set lineItems to []. "
    "- Map Dutch terms to schema keys: 'Factuurnummer'/'Factuurnr.' -> invoiceNumber; 'Factuurdatum' -> invoiceDate; "
    "  'Vervaldatum' -> dueDate; 'Subtotaal' -> subtotal; 'BTW'/'Omzetbelasting' -> tax; "
    "  'Totaal'/'Totaalbedrag'/'Te betalen' -> total; 'Omschrijving' -> lineItems.description; "
    "  'Aantal' -> lineItems.quantity; 'Prijs'/'Eenheidsprijs'/'Tarief' -> lineItems.unitPrice; 'Bedrag' -> lineItems.lineTotal; "
    "  'Valuta' -> currency. Default currency to EUR if not found. "
    "- Dates must be YYYY-MM-DD. "
    "- All numeric fields must be numbers (not strings). Use '.' as decimal separator. "
    "- Prefer totals explicitly labeled as 'Totaal', 'Total', or 'Balance Due' if multiple candidates exist. "
    "Return ONLY the JSON object. No markdown, no code fences, no commentary."
)


class LLMService:
    def __init__(self) -> None:
        self.settings = get_settings()
        # Read max output tokens from env without modifying global settings
        try:
            mot = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "4096"))
            # Clamp to a reasonable range to avoid provider errors
            self.max_output_tokens = max(256, min(8192, mot))
        except Exception:
            self.max_output_tokens = 4096

    def _gemini_url(self) -> str:
        model = self.settings.GEMINI_MODEL or "gemini-2.5-flash"
        return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.settings.GEMINI_API_KEY}"

    def _openrouter_url(self) -> str:
        return "https://openrouter.ai/api/v1/chat/completions"

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_random_exponential(multiplier=0.2, max=5),
        retry=retry_if_exception(_is_retryable),
    )
    async def _post_json(self, url: str, *, headers: Optional[Dict[str, str]] = None, payload: Dict[str, Any], timeout: float = 60.0) -> Dict[str, Any]:
        """HTTP POST JSON with retries. Raises httpx.HTTPStatusError on non-2xx.

        Returns parsed JSON dict.
        """
        t = httpx.Timeout(timeout, connect=5.0)
        async with httpx.AsyncClient(timeout=t) as client:
            resp = await client.post(url, headers=headers, json=payload)
            # Raise for non-2xx and feed status to retry predicate
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:  # rewrap with context for tenacity
                raise e
            return resp.json()

    async def parse_with_gemini_async(self, text: str) -> Dict[str, Any]:
        if not self.settings.GEMINI_API_KEY:
            raise RuntimeError("Missing GEMINI_API_KEY")
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": JSON_INSTRUCTIONS},
                        {"text": "\n---- OCR TEXT ----\n" + text[:15000]},
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": self.max_output_tokens,
                "responseMimeType": "application/json",
            },
        }
        data = await self._post_json(self._gemini_url(), payload=payload)
        # Gemini may return candidates[0].content.parts[0].text
        try:
            cands = data["candidates"][0]
            parts = cands["content"]["parts"][0]
            text_out = parts.get("text") or parts.get("inlineData", {}).get("data", "")
        except Exception as e:  # noqa: BLE001
            logger.exception("Gemini unexpected response: %s", data)
            raise RuntimeError(f"Gemini parse error: {e}")
        try:
            return json.loads(text_out)
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"Gemini returned non-JSON: {e}")

    async def parse_with_openrouter_async(self, text: str) -> Dict[str, Any]:
        if not self.settings.OPENROUTER_API_KEY:
            raise RuntimeError("Missing OPENROUTER_API_KEY")
        headers = {
            "Authorization": f"Bearer {self.settings.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.settings.OPENROUTER_MODEL or "meta-llama/llama-3.3-70b-instruct:free",
            "messages": [
                {"role": "system", "content": JSON_INSTRUCTIONS},
                {"role": "user", "content": text[:12000]},
            ],
            "temperature": 0.2,
            "max_tokens": self.max_output_tokens,
        }
        data = await self._post_json(self._openrouter_url(), headers=headers, payload=payload)
        try:
            content = data["choices"][0]["message"]["content"]
        except Exception as e:  # noqa: BLE001
            logger.exception("OpenRouter unexpected response: %s", data)
            raise RuntimeError(f"OpenRouter parse error: {e}")
        try:
            return json.loads(content)
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"OpenRouter returned non-JSON: {e}")

    async def extract_invoice_async(self, text: str) -> Dict[str, Any]:
        """Try Gemini, fallback to OpenRouter, returning parsed invoice JSON."""
        try:
            return await self.parse_with_gemini_async(text)
        except Exception as e:
            logger.warning("Gemini failed: %s", e)
        try:
            return await self.parse_with_openrouter_async(text)
        except Exception as e:
            logger.error("OpenRouter failed: %s", e)
            raise
