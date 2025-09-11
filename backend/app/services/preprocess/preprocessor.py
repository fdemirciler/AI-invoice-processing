"""PreprocessorService: builds a DOM from Vision annotations, applies zoning and
confidence filtering, optionally summarizes tables, and assembles an LLM-friendly
payload.

Design choices:
- Vision-only: relies on bounding boxes and confidences from Vision API.
- Fallbacks preferred over brittle parsing. If any step is uncertain, return
  cleaned full text for that section.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import re

from ...config import get_settings  # type: ignore  # relative to app
from .dom import BoundingBox, Word, Line, Block, Page, Document


@dataclass
class PreprocessResult:
    text: str
    table_detected: bool = False


class PreprocessorService:
    def __init__(self) -> None:
        self.settings = get_settings()

    # Public entry -----------------------------------------------------------
    def process(self, annotations: Optional[List[dict]]) -> PreprocessResult:
        if not annotations:
            # No annotations -> nothing to preprocess
            return PreprocessResult(text="")

        doc = self.build_dom(annotations)
        zones_per_page = [self.detect_zones(p) for p in doc.pages]
        self.filter_confidence(doc, zones_per_page)
        parts: List[str] = []
        any_table = False
        for idx, page in enumerate(doc.pages, start=1):
            zones = zones_per_page[idx - 1]
            header_txt = self._emit_zone_text(page, zones, "header")
            body_out, table_flag = self._emit_body(page, zones)
            footer_txt = self._emit_zone_text(page, zones, "footer")
            any_table = any_table or table_flag
            # No labels in output per requirement
            page_text = "\n".join(s for s in [header_txt, body_out, footer_txt] if s)
            parts.append(page_text)
        payload = "\n\n".join(p for p in parts if p)
        payload = self._sanitize(payload)
        # Clamp to PREPROCESS_MAX_CHARS
        max_chars = max(1000, int(self.settings.PREPROCESS_MAX_CHARS))
        if len(payload) > max_chars:
            payload = payload[:max_chars]
        return PreprocessResult(text=payload, table_detected=any_table)

    # DOM builder -----------------------------------------------------------
    def build_dom(self, annotations: List[dict]) -> Document:
        pages: List[Page] = []
        for idx, resp in enumerate(annotations, start=1):
            fta = resp.get("fullTextAnnotation") or {}
            page_dicts = fta.get("pages") or []
            # Some responses pack multiple pages per response; iterate all
            for p_i, p in enumerate(page_dicts, start=1):
                width = int(p.get("width") or 0) or 1
                height = int(p.get("height") or 0) or 1
                blocks: List[Block] = []
                for b in p.get("blocks", []) or []:
                    lines: List[Line] = []
                    # Treat paragraphs as lines (Vision v1 doesn't always provide lines)
                    for par in b.get("paragraphs", []) or []:
                        words: List[Word] = []
                        for w in par.get("words", []) or []:
                            # Word text built from symbols
                            symbols = w.get("symbols", []) or []
                            text = "".join(s.get("text", "") for s in symbols)
                            conf = float(w.get("confidence", 0.0) or 0.0)
                            bbox = BoundingBox.from_poly(
                                w.get("boundingBox", {}) or {}, width, height
                            )
                            if text:
                                words.append(Word(text=text, conf=conf, bbox=bbox))
                        if words:
                            line_bbox = BoundingBox.union([w.bbox for w in words])
                            line_conf = sum(w.conf for w in words) / max(1, len(words))
                            lines.append(Line(words=words, bbox=line_bbox, conf=line_conf))
                    if lines:
                        block_bbox = BoundingBox.union([ln.bbox for ln in lines])
                        block_conf = sum(ln.conf for ln in lines) / max(1, len(lines))
                        blocks.append(Block(lines=lines, bbox=block_bbox, conf=block_conf))
                if blocks:
                    pages.append(Page(index=len(pages) + 1, width=width, height=height, blocks=blocks))
        return Document(pages=pages)

    # Zoning ----------------------------------------------------------------
    def detect_zones(self, page: Page) -> Dict[str, Tuple[float, float]]:
        # Default: entire page is Body
        if not page.blocks:
            return {"body": (0.0, 1.0)}
        blocks = sorted(page.blocks, key=lambda b: b.bbox.y_min)
        gaps: List[Tuple[int, float]] = []  # (index, gap_size)
        for i in range(len(blocks) - 1):
            gap = blocks[i + 1].bbox.y_min - blocks[i].bbox.y_max
            gaps.append((i, max(0.0, gap)))
        # Choose up to two largest gaps above ratio threshold to split header/body/footer
        gaps_sorted = sorted(gaps, key=lambda t: t[1], reverse=True)
        min_gap = float(self.settings.PREPROCESS_ZONE_GAP_MIN_RATIO)
        top = [g for g in gaps_sorted if g[1] >= min_gap][:2]
        if not top:
            return {"body": (0.0, 1.0)}
        cuts = sorted([blocks[i].bbox.y_max for (i, _) in top])
        if len(cuts) == 1:
            c1 = cuts[0]
            return {"header": (0.0, c1), "body": (c1, 1.0)}
        c1, c2 = cuts[0], cuts[1]
        if c1 > c2:
            c1, c2 = c2, c1
        return {"header": (0.0, c1), "body": (c1, c2), "footer": (c2, 1.0)}

    # Filtering -------------------------------------------------------------
    def filter_confidence(self, doc: Document, zones_per_page: List[Dict[str, Tuple[float, float]]]) -> None:
        s = self.settings
        for p_idx, page in enumerate(doc.pages):
            zones = zones_per_page[p_idx]
            for block in page.blocks:
                new_lines: List[Line] = []
                for line in block.lines:
                    new_words: List[Word] = []
                    for w in line.words:
                        if w.conf < s.PREPROCESS_GLOBAL_CONF_MIN:
                            continue
                        # Zone-specific thresholds
                        yy = w.bbox.mid_y
                        thr = s.PREPROCESS_BODY_CONF_MIN
                        if "header" in zones and yy <= zones["header"][1]:
                            thr = s.PREPROCESS_HEADER_CONF_MIN
                        elif "footer" in zones and yy >= zones["footer"][0]:
                            thr = s.PREPROCESS_FOOTER_CONF_MIN
                        if w.conf >= thr:
                            new_words.append(w)
                    if new_words:
                        line_bbox = BoundingBox.union([w.bbox for w in new_words])
                        line_conf = sum(w.conf for w in new_words) / max(1, len(new_words))
                        new_lines.append(Line(words=new_words, bbox=line_bbox, conf=line_conf))
                if new_lines:
                    block.bbox = BoundingBox.union([ln.bbox for ln in new_lines])
                    block.conf = sum(ln.conf for ln in new_lines) / max(1, len(new_lines))
                    block.lines = new_lines
                else:
                    block.lines = []
            # remove empty blocks
            page.blocks = [b for b in page.blocks if b.lines]

    # Emission --------------------------------------------------------------
    def _emit_zone_text(self, page: Page, zones: Dict[str, Tuple[float, float]], key: str) -> str:
        if key not in zones:
            return ""
        y0, y1 = zones[key]
        texts: List[str] = []
        for blk in page.blocks:
            if blk.bbox.y_min >= y0 and blk.bbox.y_max <= y1:
                for ln in blk.lines:
                    t = ln.text.strip()
                    if t:
                        texts.append(t)
        return "\n".join(texts)

    def _emit_body(self, page: Page, zones: Dict[str, Tuple[float, float]]) -> Tuple[str, bool]:
        if "body" not in zones:
            return (self._emit_zone_text(page, {"body": (0.0, 1.0)}, "body"), False)
        y0, y1 = zones["body"]
        # Collect body lines
        body_lines: List[Line] = []
        for blk in page.blocks:
            if blk.bbox.y_min >= y0 and blk.bbox.y_max <= y1:
                body_lines.extend(blk.lines)
        # Try table summarization
        summary = self._summarize_table_if_present(body_lines)
        if summary is not None:
            return (summary, True)
        # Fallback: full body text
        body_text = "\n".join(ln.text.strip() for ln in body_lines if ln.text.strip())
        return (body_text, False)

    # Table detection & summary --------------------------------------------
    def _summarize_table_if_present(self, lines: List[Line]) -> Optional[str]:
        s = self.settings
        if len(lines) < s.PREPROCESS_TABLE_MIN_ROWS:
            return None
        # Quantize x positions to bins (helps align columns)
        def bins_for_line(ln: Line, step: float = 0.02) -> List[float]:
            xs = [w.bbox.x_min for w in ln.words]
            return sorted({round(x / step) * step for x in xs})

        rows: List[Tuple[Line, List[float]]] = []
        for ln in lines:
            b = bins_for_line(ln)
            if len(b) >= s.PREPROCESS_TABLE_MIN_COLS:
                rows.append((ln, b))
        if len(rows) < s.PREPROCESS_TABLE_MIN_ROWS:
            return None
        # Look for consecutive runs with similar bins (first 10 rows)
        best_run: List[Line] = []
        current: List[Line] = []
        last_bins: Optional[List[float]] = None
        for ln, b in rows[: min(len(rows), 40)]:
            if last_bins is None or self._bins_similar(last_bins, b):
                current.append(ln)
            else:
                if len(current) > len(best_run):
                    best_run = current
                current = [ln]
            last_bins = b
        if len(current) > len(best_run):
            best_run = current
        if len(best_run) < s.PREPROCESS_TABLE_MIN_ROWS:
            return None
        # Form header guess from the first line with header keywords (within first 5 lines)
        header_kw = self._parse_keyword_groups(s.PREPROCESS_TABLE_HEADER_KEYWORDS)
        header_text = ""
        for ln in best_run[:5]:
            low = ln.text.lower()
            if self._groups_satisfied(low, header_kw):
                header_text = ln.text.strip()
                break
        # Count interior rows (excluding header if matched)
        interior = best_run
        if header_text and interior and interior[0].text.strip() == header_text:
            interior = interior[1:]
        n_items = len(interior)
        # Extract likely totals lines from all lines (end of body often contains totals)
        total_lines = []
        for ln in lines[-10:]:
            low = ln.text.lower()
            if re.search(r"\b(subtotal|btw|tax|totaal|total|amount|bedrag)\b", low):
                total_lines.append(ln.text.strip())
        parts: List[str] = []
        if header_text:
            parts.append(header_text)
        if n_items > 0:
            parts.append(f"...[{n_items} line items summarized]...")
        if total_lines:
            parts.extend(total_lines)
        out = "\n".join(p for p in parts if p)
        return out or None

    @staticmethod
    def _bins_similar(a: List[float], b: List[float], tol: float = 0.04) -> bool:
        if not a or not b:
            return False
        # Simple Jaccard-like check with tolerance: treat values within tol as equal
        def merge(vals: List[float]) -> List[float]:
            vals = sorted(vals)
            merged: List[float] = []
            for v in vals:
                if not merged or abs(v - merged[-1]) > tol:
                    merged.append(v)
            return merged
        aa = merge(a)
        bb = merge(b)
        inter = 0
        i = j = 0
        while i < len(aa) and j < len(bb):
            if abs(aa[i] - bb[j]) <= tol:
                inter += 1
                i += 1
                j += 1
            elif aa[i] < bb[j]:
                i += 1
            else:
                j += 1
        denom = max(len(aa), len(bb))
        return inter >= max(2, int(0.6 * denom))

    @staticmethod
    def _parse_keyword_groups(raw: str) -> List[List[str]]:
        groups: List[List[str]] = []
        if not raw:
            return groups
        # Support both ';' and ':' as group separators to avoid .env escaping issues
        for grp in re.split(r"[;:]", raw):
            tokens = [t.strip().lower() for t in grp.split("|") if t.strip()]
            if tokens:
                groups.append(tokens)
        return groups

    @staticmethod
    def _groups_satisfied(text_lower: str, groups: List[List[str]]) -> bool:
        if not groups:
            return True
        for grp in groups:
            if not any(tok in text_lower for tok in grp):
                return False
        return True

    @staticmethod
    def _sanitize(text: str) -> str:
        # Collapse whitespace and trim
        text = re.sub(r"[ \t\f\v]+", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()
