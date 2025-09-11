"""Lightweight Document Object Model built from Vision API annotations.

This DOM uses normalized coordinates [0, 1] so it is independent from page width/height.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class BoundingBox:
    """Axis-aligned bounding box with normalized coordinates in [0, 1]."""
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    @property
    def width(self) -> float:
        return max(0.0, self.x_max - self.x_min)

    @property
    def height(self) -> float:
        return max(0.0, self.y_max - self.y_min)

    @property
    def mid_y(self) -> float:
        return (self.y_min + self.y_max) / 2.0

    @staticmethod
    def from_poly(poly: dict, page_width: float, page_height: float) -> "BoundingBox":
        # Prefer normalizedVertices when present
        verts = poly.get("normalizedVertices")
        if verts:
            xs = [float(v.get("x", 0.0)) for v in verts]
            ys = [float(v.get("y", 0.0)) for v in verts]
            return BoundingBox(min(xs), min(ys), max(xs), max(ys))
        # Fallback: pixel vertices -> normalize
        verts = poly.get("vertices") or []
        w = max(1.0, float(page_width or 1.0))
        h = max(1.0, float(page_height or 1.0))
        xs = [float(v.get("x", 0.0)) / w for v in verts]
        ys = [float(v.get("y", 0.0)) / h for v in verts]
        if not xs or not ys:
            return BoundingBox(0.0, 0.0, 1.0, 1.0)
        return BoundingBox(min(xs), min(ys), max(xs), max(ys))

    @staticmethod
    def union(items: List["BoundingBox"]) -> "BoundingBox":
        if not items:
            return BoundingBox(0.0, 0.0, 0.0, 0.0)
        return BoundingBox(
            min(bb.x_min for bb in items),
            min(bb.y_min for bb in items),
            max(bb.x_max for bb in items),
            max(bb.y_max for bb in items),
        )


@dataclass
class Word:
    text: str
    conf: float
    bbox: BoundingBox


@dataclass
class Line:
    words: List[Word] = field(default_factory=list)
    bbox: BoundingBox = field(default_factory=lambda: BoundingBox(0.0, 0.0, 0.0, 0.0))
    conf: float = 0.0

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words if w.text)


@dataclass
class Block:
    lines: List[Line] = field(default_factory=list)
    bbox: BoundingBox = field(default_factory=lambda: BoundingBox(0.0, 0.0, 0.0, 0.0))
    conf: float = 0.0


@dataclass
class Page:
    index: int
    width: int
    height: int
    blocks: List[Block] = field(default_factory=list)


@dataclass
class Document:
    pages: List[Page] = field(default_factory=list)
