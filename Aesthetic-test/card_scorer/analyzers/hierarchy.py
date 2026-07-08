"""Visual Hierarchy Analyzer.

Analyzes visual weight distribution and size hierarchy:
- Visual center offset (head-heavy / lopsided)
- Quadrant density balance
- Heading-body size ratio
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from card_scorer.models import ScoringContext, TextElement

logger = logging.getLogger(__name__)


def compute_visual_center_offset(
    visual_center: tuple[float, float],
) -> dict[str, Any]:
    """Compute how far the visual center deviates from the geometric center.

    Args:
        visual_center: (cx, cy) normalized to [0, 1].

    Returns:
        {"offset_x": float, "offset_y": float, "offset_norm": float}
    """
    dx = visual_center[0] - 0.5
    dy = visual_center[1] - 0.5
    norm = (dx**2 + dy**2) ** 0.5
    return {"offset_x": dx, "offset_y": dy, "offset_norm": norm}


def compute_density_balance(
    quadrant_density: dict[str, float],
) -> dict[str, Any]:
    """Compute the ratio between the densest and sparsest quadrant.

    Returns:
        {"max_quadrant": str, "min_quadrant": str, "ratio": float}
    """
    if not quadrant_density:
        return {"max_quadrant": "", "min_quadrant": "", "ratio": 1.0}

    max_q = max(quadrant_density, key=quadrant_density.get)  # type: ignore[arg-type]
    min_q = min(quadrant_density, key=quadrant_density.get)  # type: ignore[arg-type]
    max_val = quadrant_density[max_q]
    min_val = quadrant_density[min_q]
    ratio = max_val / min_val if min_val > 0 else float("inf")

    return {"max_quadrant": max_q, "min_quadrant": min_q, "ratio": ratio}


def compute_size_hierarchy(
    text_elements: list[TextElement],
) -> dict[str, Any]:
    """Check heading-body font size ratio.

    Assumes the largest text is the heading and the median is body text.

    Returns:
        {"max_size": float, "median_size": float, "ratio": float}
    """
    if len(text_elements) < 2:
        return {"max_size": 0.0, "median_size": 0.0, "ratio": 1.0}

    sizes = [e.font_size_est or e.bbox.height for e in text_elements]
    max_size = float(max(sizes))
    median_size = float(np.median(sizes))
    ratio = max_size / median_size if median_size > 0 else 1.0

    return {"max_size": max_size, "median_size": median_size, "ratio": ratio}


def analyze(ctx: ScoringContext) -> None:
    """Run hierarchy analyses and store in ctx.features."""
    visual_center = ctx.features.get("visual_center", (0.5, 0.5))
    quadrant_density = ctx.features.get("quadrant_density", {})

    ctx.features["visual_center_offset"] = compute_visual_center_offset(visual_center)
    ctx.features["density_balance"] = compute_density_balance(quadrant_density)
    ctx.features["size_hierarchy"] = compute_size_hierarchy(ctx.text_elements)
    logger.info("Hierarchy analysis complete.")
