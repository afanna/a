"""Visual Consistency Analyzer.

This is the CORE of Phase 2 -- the features humans are most sensitive to:
1. Alignment consistency (horizontal/vertical alignment clusters)
2. Spacing consistency (variance of inter-element gaps)
3. Font rhythm (font size level distribution)
4. Component rhythm (regularity of component spacing)
5. Icon proportion (icon area vs card area)
6. Text-image ratio
7. Margin consistency (left/right margin symmetry)
8. Grid alignment
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

import numpy as np

from card_scorer.configs.loader import Config
from card_scorer.models import BBox, ComponentElement, ScoringContext, TextElement

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Alignment consistency
# ---------------------------------------------------------------------------

def compute_alignment_clusters(
    elements: list[TextElement | ComponentElement],
    eps: float = 5.0,
) -> dict[str, Any]:
    """Cluster left-edges and top-edges to detect alignment axes.

    Uses a simple 1D clustering: sort edges, group consecutive values
    within ``eps`` pixels.

    Returns:
        {
            "left_clusters": [[edge_values], ...],
            "top_clusters": [[edge_values], ...],
            "num_left_clusters": int,
            "num_top_clusters": int,
            "outlier_ratio": float,  # elements not in the dominant cluster
        }
    """
    def _cluster_1d(values: list[float], eps: float) -> list[list[float]]:
        if not values:
            return []
        sorted_vals = sorted(values)
        clusters: list[list[float]] = [[sorted_vals[0]]]
        for v in sorted_vals[1:]:
            if v - clusters[-1][-1] <= eps:
                clusters[-1].append(v)
            else:
                clusters.append([v])
        return clusters

    left_edges = [e.bbox.x1 for e in elements]
    top_edges = [e.bbox.y1 for e in elements]

    left_clusters = _cluster_1d(left_edges, eps)
    top_clusters = _cluster_1d(top_edges, eps)

    # Outlier ratio: elements not in the largest left-alignment cluster
    if left_clusters:
        largest = max(len(c) for c in left_clusters)
        outlier_ratio = 1.0 - largest / max(len(left_edges), 1)
    else:
        outlier_ratio = 0.0

    return {
        "left_clusters": left_clusters,
        "top_clusters": top_clusters,
        "num_left_clusters": len(left_clusters),
        "num_top_clusters": len(top_clusters),
        "outlier_ratio": outlier_ratio,
    }


# ---------------------------------------------------------------------------
# 2. Spacing consistency
# ---------------------------------------------------------------------------

def compute_spacing_variance(
    elements: list[TextElement | ComponentElement],
) -> dict[str, Any]:
    """Compute variance of vertical gaps between consecutive elements (sorted by y).

    Returns:
        {
            "gaps": [float, ...],
            "mean_gap": float,
            "std_gap": float,
            "cv": float,  # coefficient of variation (std/mean)
            "sample_size": int,  # number of gaps (elements - 1)
        }
    """
    if len(elements) < 2:
        return {"gaps": [], "mean_gap": 0.0, "std_gap": 0.0, "cv": 0.0, "sample_size": 0}

    sorted_elems = sorted(elements, key=lambda e: e.bbox.y1)
    gaps = []
    for i in range(1, len(sorted_elems)):
        gap = sorted_elems[i].bbox.y1 - sorted_elems[i - 1].bbox.y2
        gaps.append(gap)

    arr = np.array(gaps)
    mean_gap = float(np.mean(arr))
    std_gap = float(np.std(arr))
    cv = std_gap / mean_gap if mean_gap > 0 else 0.0

    return {
        "gaps": gaps,
        "mean_gap": mean_gap,
        "std_gap": std_gap,
        "cv": cv,
        "sample_size": len(gaps),
    }


# ---------------------------------------------------------------------------
# 3. Font rhythm
# ---------------------------------------------------------------------------

def compute_font_rhythm(
    text_elements: list[TextElement],
) -> dict[str, Any]:
    """Analyze font size levels.

    Returns:
        {
            "size_levels": int,  # number of distinct font size buckets
            "sizes": [float, ...],
            "size_counts": {bucket: count},
        }
    """
    if not text_elements:
        return {"size_levels": 0, "sizes": [], "size_counts": {}}

    sizes = [e.font_size_est or e.bbox.height for e in text_elements]
    # Bucket to nearest 2px to avoid noise
    bucketed = [round(s / 2) * 2 for s in sizes]
    counts = Counter(bucketed)

    return {
        "size_levels": len(counts),
        "sizes": sizes,
        "size_counts": dict(counts),
    }


# ---------------------------------------------------------------------------
# 4. Component rhythm
# ---------------------------------------------------------------------------

def compute_component_rhythm(
    components: list[ComponentElement],
) -> dict[str, Any]:
    """Analyze spacing regularity among non-text components.

    Returns same structure as spacing_variance but for components only.
    """
    if len(components) < 2:
        return {"gaps": [], "mean_gap": 0.0, "std_gap": 0.0, "cv": 0.0, "sample_size": 0}

    sorted_comps = sorted(components, key=lambda c: c.bbox.y1)
    gaps = []
    for i in range(1, len(sorted_comps)):
        gap = sorted_comps[i].bbox.y1 - sorted_comps[i - 1].bbox.y2
        gaps.append(gap)

    arr = np.array(gaps)
    mean_gap = float(np.mean(arr))
    std_gap = float(np.std(arr))
    cv = std_gap / mean_gap if mean_gap > 0 else 0.0

    return {
        "gaps": gaps,
        "mean_gap": mean_gap,
        "std_gap": std_gap,
        "cv": cv,
        "sample_size": len(gaps),
    }


# ---------------------------------------------------------------------------
# 5. Icon proportion
# ---------------------------------------------------------------------------

def compute_icon_proportion(
    components: list[ComponentElement],
    image_width: int,
    image_height: int,
) -> dict[str, Any]:
    """Compute total icon/component area as a proportion of image area.

    Returns: {"total_icon_area": float, "image_area": float, "ratio": float}
    """
    image_area = image_width * image_height
    total_icon = sum(c.area for c in components)
    ratio = total_icon / image_area if image_area > 0 else 0.0
    return {"total_icon_area": total_icon, "image_area": float(image_area), "ratio": ratio}


# ---------------------------------------------------------------------------
# 6. Text-image ratio
# ---------------------------------------------------------------------------

def compute_text_image_ratio(
    text_elements: list[TextElement],
    components: list[ComponentElement],
) -> float:
    """Ratio of total text area to total non-text area.

    Returns a value in [0, inf). 0 means no text.
    """
    text_area = sum(e.bbox.area for e in text_elements)
    comp_area = sum(c.area for c in components)
    total = text_area + comp_area
    if total <= 0:
        return 0.0
    return text_area / total


# ---------------------------------------------------------------------------
# 7. Margin consistency
# ---------------------------------------------------------------------------

def compute_margin_consistency(
    elements: list[TextElement | ComponentElement],
    image_width: int,
) -> dict[str, Any]:
    """Check if left and right margins are consistent across elements.

    Returns:
        {
            "left_margins": [float, ...],
            "right_margins": [float, ...],
            "left_cv": float,
            "right_cv": float,
            "lr_diff_ratio": float,  # |mean_left - mean_right| / image_width
            "sample_size": int,
        }
    """
    if not elements:
        return {
            "left_margins": [], "right_margins": [],
            "left_cv": 0.0, "right_cv": 0.0, "lr_diff_ratio": 0.0,
            "sample_size": 0,
        }

    left_margins = [e.bbox.x1 for e in elements]
    right_margins = [image_width - e.bbox.x2 for e in elements]

    def _cv(arr: list[float]) -> float:
        a = np.array(arr)
        m = np.mean(a)
        return float(np.std(a) / m) if m > 0 else 0.0

    mean_l = float(np.mean(left_margins))
    mean_r = float(np.mean(right_margins))
    lr_diff = abs(mean_l - mean_r) / image_width if image_width > 0 else 0.0

    return {
        "left_margins": left_margins,
        "right_margins": right_margins,
        "left_cv": _cv(left_margins),
        "right_cv": _cv(right_margins),
        "lr_diff_ratio": lr_diff,
        "sample_size": len(elements),
    }


# ---------------------------------------------------------------------------
# 8. Grid alignment
# ---------------------------------------------------------------------------

def compute_grid_alignment(
    elements: list[TextElement | ComponentElement],
    eps: float = 5.0,
) -> dict[str, Any]:
    """Measure how well elements snap to an implicit grid.

    Returns:
        {
            "x_snap_ratio": float,  # fraction of elements on an x-grid line
            "y_snap_ratio": float,
        }
    """
    if not elements:
        return {"x_snap_ratio": 1.0, "y_snap_ratio": 1.0}

    left_edges = [e.bbox.x1 for e in elements]
    top_edges = [e.bbox.y1 for e in elements]

    def _snap_ratio(values: list[float], eps: float) -> float:
        """Fraction of values that share a position (within eps) with at least one other."""
        n = len(values)
        if n <= 1:
            return 1.0
        snapped = 0
        sorted_v = sorted(values)
        for i, v in enumerate(sorted_v):
            for j in range(i + 1, n):
                if sorted_v[j] - v > eps:
                    break
                if abs(sorted_v[j] - v) <= eps:
                    snapped += 1
                    break
        return snapped / n

    return {
        "x_snap_ratio": _snap_ratio(left_edges, eps),
        "y_snap_ratio": _snap_ratio(top_edges, eps),
    }


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

def analyze(ctx: ScoringContext) -> None:
    """Run all consistency analyses and store in ctx.features."""
    cfg = Config.load()
    eps = cfg.threshold("consistency", "alignment_cluster_eps")

    all_elements: list[TextElement | ComponentElement] = (
        ctx.text_elements + ctx.component_elements  # type: ignore[operator]
    )

    ctx.features["alignment"] = compute_alignment_clusters(all_elements, eps=eps)
    ctx.features["spacing"] = compute_spacing_variance(all_elements)
    ctx.features["font_rhythm"] = compute_font_rhythm(ctx.text_elements)
    ctx.features["component_rhythm"] = compute_component_rhythm(ctx.component_elements)
    ctx.features["icon_proportion"] = compute_icon_proportion(
        ctx.component_elements, ctx.image_width, ctx.image_height
    )
    ctx.features["text_image_ratio"] = compute_text_image_ratio(
        ctx.text_elements, ctx.component_elements
    )
    ctx.features["margin_consistency"] = compute_margin_consistency(
        all_elements, ctx.image_width
    )
    ctx.features["grid_alignment"] = compute_grid_alignment(all_elements, eps=eps)
    logger.info("Consistency analysis complete.")
