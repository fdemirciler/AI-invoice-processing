"""LLM service: Gemini primary, OpenRouter fallback, returning strict JSON.

This module provides a minimal wrapper around HTTP APIs using requests.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

import requests

from ..config import get_settings

logger = logging.getLogger(__name__)


JSON_INSTRUCTIONS = (
    "You are an information extraction engine. Extract invoice data as strict JSON with keys: "
    "invoiceNumber (string), invoiceDate (YYYY-MM-DD), vendorName (string), currency (ISO code), "
    "subtotal (number), tax (number), total (number), dueDate (YYYY-MM-DD or null), "
    "lineItems (array of {description, quantity, unitPrice, lineTotal}), notes (optional). "
    "Return ONLY JSON. No markdown, no prose."
)


class LLMService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _gemini_url(self) -> str:
        model = self.settings.GEMINI_MODEL or "gemini-2.5-flash"
        return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.settings.GEMINI_API_KEY}"

    def _openrouter_url(self) -> str:
        return "https://openrouter.ai/api/v1/chat/completions"

    def parse_with_gemini(self, text: str) -> Dict[str, Any]:
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
                "maxOutputTokens": 2048,
                "responseMimeType": "application/json",
            },
        }
        resp = requests.post(self._gemini_url(), json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
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

    def parse_with_openrouter(self, text: str) -> Dict[str, Any]:
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
        }
        resp = requests.post(self._openrouter_url(), headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except Exception as e:  # noqa: BLE001
            logger.exception("OpenRouter unexpected response: %s", data)
            raise RuntimeError(f"OpenRouter parse error: {e}")
        try:
            return json.loads(content)
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"OpenRouter returned non-JSON: {e}")

    def extract_invoice(self, text: str) -> Dict[str, Any]:
        # Try Gemini first
        try:
            return self.parse_with_gemini(text)
        except Exception as e:
            logger.warning("Gemini failed: %s", e)
        # Fallback to OpenRouter
        try:
            return self.parse_with_openrouter(text)
        except Exception as e:
            logger.error("OpenRouter failed: %s", e)
            raise
