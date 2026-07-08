"""Geometry Analyzer.

Computes spatial/layout features from extracted elements:
- Edge distances (margin to card boundary)
- Overlap detection (IoU between elements)
- Whitespace ratio
- Element overflow detection
- Visual center of mass
- Quadrant density distribution
"""

from __future__ import annotations

import logging
from typing import Any

import cv2
import numpy as np

from card_scorer.models import BBox, ComponentElement, ScoringContext, TextElement

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Edge / margin analysis
# ---------------------------------------------------------------------------

def compute_edge_distances(
    elements: list[TextElement | ComponentElement],
    image_width: int,
    image_height: int,
) -> list[dict[str, Any]]:
    """Compute distance from each element to the four edges of the card.

    Returns a list of dicts with keys:
        element_index, bbox, left, top, right, bottom, min_distance
    """
    results = []
    for i, elem in enumerate(elements):
        bbox = elem.bbox
        left = bbox.x1
        top = bbox.y1
        right = image_width - bbox.x2
        bottom = image_height - bbox.y2
        min_dist = min(left, top, right, bottom)
        results.append({
            "element_index": i,
            "bbox": bbox,
            "left": left,
            "top": top,
            "right": right,
            "bottom": bottom,
            "min_distance": min_dist,
        })
    return results


# ---------------------------------------------------------------------------
# Overlap detection
# ---------------------------------------------------------------------------

def compute_overlaps(
    elements: list[TextElement | ComponentElement],
    iou_threshold: float = 0.05,
) -> list[dict[str, Any]]:
    """Find overlapping element pairs exceeding an IoU threshold.

    Returns list of dicts with keys: idx_a, idx_b, iou.
    """
    overlaps = []
    for i in range(len(elements)):
        for j in range(i + 1, len(elements)):
            iou = elements[i].bbox.iou(elements[j].bbox)
            if iou > iou_threshold:
                overlaps.append({"idx_a": i, "idx_b": j, "iou": iou})
    return overlaps


# ---------------------------------------------------------------------------
# Whitespace ratio
# ---------------------------------------------------------------------------

def compute_whitespace_ratio(
    elements: list[TextElement | ComponentElement],
    image_width: int,
    image_height: int,
) -> float:
    """Estimate whitespace ratio as 1 - (union of element areas / image area).

    A rough estimate that treats each element bbox as opaque.
    """
    image_area = image_width * image_height
    if image_area <= 0:
        return 0.0

    # Create a mask and paint element bboxes
    mask = np.zeros((image_height, image_width), dtype=np.uint8)
    for elem in elements:
        b = elem.bbox
        x1, y1 = max(0, int(b.x1)), max(0, int(b.y1))
        x2, y2 = min(image_width, int(b.x2)), min(image_height, int(b.y2))
        mask[y1:y2, x1:x2] = 1

    occupied = int(np.sum(mask))
    return 1.0 - (occupied / image_area)


# ---------------------------------------------------------------------------
# Element overflow
# ---------------------------------------------------------------------------

def detect_overflow(
    elements: list[TextElement | ComponentElement],
    image_width: int,
    image_height: int,
) -> list[dict[str, Any]]:
    """Detect elements whose bboxes extend beyond image boundaries."""
    overflows = []
    for i, elem in enumerate(elements):
        b = elem.bbox
        overflow_info: dict[str, float] = {}
        if b.x1 < 0:
            overflow_info["left"] = abs(b.x1)
        if b.y1 < 0:
            overflow_info["top"] = abs(b.y1)
        if b.x2 > image_width:
            overflow_info["right"] = b.x2 - image_width
        if b.y2 > image_height:
            overflow_info["bottom"] = b.y2 - image_height
        if overflow_info:
            overflows.append({"element_index": i, "overflow": overflow_info})
    return overflows


# ---------------------------------------------------------------------------
# Visual center of mass
# ---------------------------------------------------------------------------

def compute_visual_center(image: np.ndarray) -> tuple[float, float]:
    """Compute normalized visual center of mass using image moments.

    Returns (cx, cy) in range [0, 1] relative to image dimensions.
    (0.5, 0.5) is the geometric center.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # Invert so foreground contributes
    inverted = 255 - gray
    moments = cv2.moments(inverted)
    total = moments["m00"]
    if total <= 0:
        return (0.5, 0.5)

    h, w = image.shape[:2]
    cx = moments["m10"] / total / w
    cy = moments["m01"] / total / h
    return (cx, cy)


# ---------------------------------------------------------------------------
# Quadrant density
# ---------------------------------------------------------------------------

def compute_quadrant_density(
    elements: list[TextElement | ComponentElement],
    image_width: int,
    image_height: int,
) -> dict[str, float]:
    """Compute element area density in each quadrant (2x2 grid).

    Returns dict with keys: top_left, top_right, bottom_left, bottom_right.
    Values are total element area in that quadrant.
    """
    mid_x = image_width / 2
    mid_y = image_height / 2
    density = {"top_left": 0.0, "top_right": 0.0, "bottom_left": 0.0, "bottom_right": 0.0}

    for elem in elements:
        cx, cy = elem.bbox.center
        area = elem.bbox.area
        if cx <= mid_x and cy <= mid_y:
            density["top_left"] += area
        elif cx > mid_x and cy <= mid_y:
            density["top_right"] += area
        elif cx <= mid_x and cy > mid_y:
            density["bottom_left"] += area
        else:
            density["bottom_right"] += area

    return density


# ---------------------------------------------------------------------------
# Aggregate feature computation
# ---------------------------------------------------------------------------

def analyze(ctx: ScoringContext, image: np.ndarray) -> None:
    """Run all geometry analyses and store results in ctx.features."""
    all_elements: list[TextElement | ComponentElement] = (
        ctx.text_elements + ctx.component_elements  # type: ignore[operator]
    )

    ctx.features["edge_distances"] = compute_edge_distances(
        all_elements, ctx.image_width, ctx.image_height
    )
    ctx.features["overlaps"] = compute_overlaps(all_elements)
    ctx.features["whitespace_ratio"] = compute_whitespace_ratio(
        all_elements, ctx.image_width, ctx.image_height
    )
    ctx.features["overflows"] = detect_overflow(
        all_elements, ctx.image_width, ctx.image_height
    )
    ctx.features["visual_center"] = compute_visual_center(image)
    ctx.features["quadrant_density"] = compute_quadrant_density(
        all_elements, ctx.image_width, ctx.image_height
    )
    logger.info("Geometry analysis complete.")
