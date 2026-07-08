"""Aesthetics Analyzer.

Color harmony and contrast analysis:
- Dominant color count
- Color conflicts (complementary hue clash)
- High saturation detection
- WCAG contrast ratio
"""

from __future__ import annotations

import colorsys
import logging
from typing import Any

from card_scorer.configs.loader import Config
from card_scorer.models import ColorInfo, ScoringContext

logger = logging.getLogger(__name__)


def _relative_luminance(r: int, g: int, b: int) -> float:
    """WCAG 2.0 relative luminance."""
    def _linearize(c: int) -> float:
        s = c / 255.0
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    return 0.2126 * _linearize(r) + 0.7152 * _linearize(g) + 0.0722 * _linearize(b)


def contrast_ratio(rgb1: tuple[int, int, int], rgb2: tuple[int, int, int]) -> float:
    """WCAG contrast ratio between two RGB colors."""
    l1 = _relative_luminance(*rgb1)
    l2 = _relative_luminance(*rgb2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def detect_color_conflicts(
    colors: list[ColorInfo],
    hue_threshold: float = 30.0,
) -> list[dict[str, Any]]:
    """Find pairs of dominant colors with potentially conflicting hues.

    Two colors conflict if their hue distance is near 180 degrees
    (complementary) and both have significant saturation.
    """
    conflicts = []
    for i in range(len(colors)):
        for j in range(i + 1, len(colors)):
            h1 = colors[i].hsv[0] * 360
            h2 = colors[j].hsv[0] * 360
            s1 = colors[i].hsv[1]
            s2 = colors[j].hsv[1]
            hue_dist = abs(h1 - h2)
            if hue_dist > 180:
                hue_dist = 360 - hue_dist
            # Conflict = near-complementary with high saturation
            if abs(hue_dist - 180) < hue_threshold and s1 > 0.3 and s2 > 0.3:
                conflicts.append({
                    "color_a": colors[i].rgb,
                    "color_b": colors[j].rgb,
                    "hue_distance": hue_dist,
                })
    return conflicts


def detect_high_saturation(
    colors: list[ColorInfo],
    max_saturation: float = 0.9,
) -> list[dict[str, Any]]:
    """Find overly saturated dominant colors."""
    results = []
    for c in colors:
        if c.hsv[1] > max_saturation:
            results.append({
                "rgb": c.rgb,
                "saturation": c.hsv[1],
                "proportion": c.proportion,
            })
    return results


def compute_min_contrast(
    colors: list[ColorInfo],
) -> dict[str, Any]:
    """Find the minimum contrast ratio among the top dominant color pairs.

    Useful for text-on-background readability checks.
    """
    if len(colors) < 2:
        return {"min_ratio": 21.0, "pair": []}

    min_ratio = float("inf")
    min_pair: list[tuple[int, int, int]] = []
    for i in range(len(colors)):
        for j in range(i + 1, len(colors)):
            cr = contrast_ratio(colors[i].rgb, colors[j].rgb)
            if cr < min_ratio:
                min_ratio = cr
                min_pair = [colors[i].rgb, colors[j].rgb]

    return {"min_ratio": min_ratio, "pair": min_pair}


def analyze(ctx: ScoringContext) -> None:
    """Run color/aesthetic analyses and store in ctx.features."""
    cfg = Config.load()
    colors = ctx.dominant_colors

    ctx.features["color_count"] = len(colors)
    ctx.features["color_conflicts"] = detect_color_conflicts(
        colors,
        hue_threshold=cfg.threshold("color", "hue_conflict_threshold"),
    )
    ctx.features["high_saturation"] = detect_high_saturation(
        colors,
        max_saturation=cfg.threshold("color", "saturation_max"),
    )
    ctx.features["min_contrast"] = compute_min_contrast(colors)
    logger.info("Aesthetics/color analysis complete.")
