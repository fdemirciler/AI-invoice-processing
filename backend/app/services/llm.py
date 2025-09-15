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

# Default prompt (v1). Additional versions can be added to PROMPTS below.
JSON_INSTRUCTIONS = (
    """### ROLE ###
You are a highly accurate invoice data extraction engine.

### CONTEXT ###
The user will provide text that has been OCR'd from a PDF invoice. The text may 
be messy, incomplete, and can be in English or Dutch (Nederlands).

### OBJECTIVE ###
Your sole mission is to extract the key information from the text and format it 
as a SINGLE, PERFECTLY FORMED JSON object that adheres to the schema below. Do 
not output anything other than the JSON object itself.

### JSON SCHEMA ###
{
  "invoiceNumber": "string",      // REQUIRED. The main invoice identifier.
  "invoiceDate": "YYYY-MM-DD",    // REQUIRED. The date the invoice was issued.
  "vendorName": "string",         // REQUIRED. The name of the company that SENT
                                  // the invoice.
  "currency": "string",           // 3-letter ISO code, e.g., "EUR" or "USD".
                                  // Default to "EUR".
  "subtotal": "number",           // The total amount before tax.
  "tax": "number",                // The total tax amount (VAT/BTW).
  "total": "number",              // The final amount due.
  "dueDate": "YYYY-MM-DD | null", // The payment due date.
  "lineItems": [                  // An array of items or services.
    {
      "description": "string",
      "quantity": "number",
      "unitPrice": "number",
      "lineTotal": "number"
    }
  ],
  "notes": "string | null"        // Any additional notes or terms.
}

### DETAILED INSTRUCTIONS & RULES ###
- Handle Missing Required Fields:  
  If you cannot find a value for a REQUIRED field (`invoiceNumber`, 
  `invoiceDate`, `vendorName`), return `null` instead of omitting it. This 
  ensures schema consistency.

- Identify the Vendor Correctly:  
  `vendorName` must be the entity that ISSUED or SENT the invoice. Do not 
  confuse it with the customer or "Bill To" address.

- Language Mapping (Dutch → English):  
  - Factuurnummer / Factuurnr. → invoiceNumber  
  - Factuurdatum → invoiceDate  
  - Vervaldatum → dueDate  
  - Subtotaal → subtotal  
  - BTW / Omzetbelasting → tax  
  - Totaal / Totaalbedrag / Te betalen → total  

- Formatting:  
  - Dates must be in `YYYY-MM-DD` format.  
  - Numbers must be plain numbers (e.g., `1234.56`), not strings.  
    Use `.` for decimals. Do not include currency symbols or thousands 
    separators.  

- Line Items:  
  - Accurately parse each distinct item.  
  - If a summary marker like `...[N line items summarized]...` is present, 
    return an empty array `[]` for `lineItems`.  
  - Ignore non-item lines like "Subtotal" or "Discount" when creating 
    the `lineItems` array.  

- Final Output:  
  Your response MUST be ONLY the JSON object.  
  Do **not** wrap it in markdown code fences (```json), and do **not** add 
  any explanatory text before or after it.
"""
)


# Registry of prompts by version label. Extendable without code churn elsewhere.
PROMPTS = {
    "v1": JSON_INSTRUCTIONS,
}


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
        # Select prompt by version (defaults to v1)
        self.prompt_version = (self.settings.LLM_PROMPT_VERSION or "v1").strip()
        self.instructions = PROMPTS.get(self.prompt_version, JSON_INSTRUCTIONS)

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
                        {"text": self.instructions},
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
                {"role": "system", "content": self.instructions},
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
