"""Preprocessor service to prune OCR text before sending to an LLM.

It performs:
- Page-level filtering: keep only pages that look invoice-relevant.
- Line-level filtering: keep only informative lines (keywords, dates, amounts).
- Final clamp: limit overall size to a configurable character bound.

Defaults are tuned for English and Dutch and can be overridden via env.
"""
from __future__ import annotations

import re
from typing import List

from ..config import get_settings


class PreprocessorService:
    """A service to prune and clean OCR text prior to LLM extraction."""

    def __init__(self) -> None:
        settings = get_settings()
        # Compile patterns from settings for performance
        self._min_pages_to_filter = settings.PREPROC_MIN_PAGES_TO_FILTER
        self._page_filter_pattern = re.compile(settings.PREPROC_PAGE_KEYWORDS, re.IGNORECASE)
        self._line_keyword_pattern = re.compile(settings.PREPROC_LINE_KEYWORDS, re.IGNORECASE)
        self._date_pattern = re.compile(settings.PREPROC_DATE_REGEX)
        self._amount_pattern = re.compile(settings.PREPROC_AMOUNT_REGEX)
        self._max_chars = settings.PREPROC_MAX_CHARS

    def prune_and_prepare(self, pages: List[str]) -> str:
        """Run page filtering then line filtering and clamp the final text.

        Args:
            pages: A list of page texts. Empty strings are allowed.

        Returns:
            A pruned string suitable to pass to the LLM prompt.
        """
        pages = pages or []
        filtered_pages = self._filter_pages(pages)
        pruned_text = self._filter_lines("\n".join(filtered_pages))
        if len(pruned_text) > self._max_chars:
            pruned_text = pruned_text[: self._max_chars]
        return pruned_text

    def _filter_pages(self, pages: List[str]) -> List[str]:
        """Keep only pages that contain invoice-related signals.

        For very short documents (<= min_pages_to_filter), skip page filtering.
        If no pages match, keep the first min_pages_to_filter pages as a fallback.
        """
        if len(pages) <= self._min_pages_to_filter:
            return pages

        relevant = [p for p in pages if p and self._page_filter_pattern.search(p)]
        if not relevant:
            return pages[: self._min_pages_to_filter]
        return relevant

    def _filter_lines(self, text: str) -> str:
        """Keep lines that match line keywords, dates, or amounts.

        Skips empty/whitespace-only lines. Keeps first occurrence of a line; de-duplicates
        exact repeats to reduce headers/footers noise.
        """
        if not text:
            return ""

        seen = set()
        kept: List[str] = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            if line in seen:
                continue
            if (
                self._line_keyword_pattern.search(line)
                or self._date_pattern.search(line)
                or self._amount_pattern.search(line)
            ):
                kept.append(line)
                seen.add(line)
        return "\n".join(kept)
