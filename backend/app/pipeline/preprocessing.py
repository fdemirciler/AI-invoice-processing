from __future__ import annotations

import re
import unicodedata


def sanitize_for_llm(text: str, max_chars: int, strip_top: int, strip_bottom: int) -> str:
    """Lightweight sanitizer that preserves line breaks for the LLM.

    Steps:
    1) Ultra-light zoning: optionally drop top/bottom lines to remove boilerplate.
    2) Line-wise normalization and expanded noise removal (keeps newlines).
    3) Smart truncation at a newline boundary when possible.
    """
    # 1) Ultra-Light Zoning
    lines = text.splitlines()
    if strip_top < 0:
        strip_top = 0
    if strip_bottom < 0:
        strip_bottom = 0
    if len(lines) > (strip_top + strip_bottom + 5):  # avoid on very short docs
        end_idx = len(lines) - strip_bottom if strip_bottom > 0 else len(lines)
        lines = lines[strip_top:end_idx]

    # 2) Line-wise normalization and noise removal
    norm_lines = []
    for ln in lines:
        ln = unicodedata.normalize("NFKC", ln)
        ln = re.sub(r"[ \t\f\v]+", " ", ln).strip()
        if ln:
            norm_lines.append(ln)
    text2 = "\n".join(norm_lines)

    noise_patterns = [
        re.compile(r"\bPage \d+ of \d+\b", re.IGNORECASE),
        re.compile(r"Invoice scanned by.*", re.IGNORECASE),
        re.compile(r"\bConfidential\b", re.IGNORECASE),
    ]
    for pat in noise_patterns:
        text2 = pat.sub("", text2)
    # Trim any empty lines introduced by removals
    text2 = "\n".join([seg.strip() for seg in text2.splitlines() if seg.strip()])

    # 3) Smart truncation
    max_chars = max(1000, int(max_chars))
    if len(text2) > max_chars:
        cut = text2.rfind("\n", 0, max_chars)
        text2 = text2[:cut] if cut != -1 else text2[:max_chars]

    return text2
