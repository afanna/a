from __future__ import annotations

import numpy as np

from ..math_utils import coefficient_of_variation, gaussian_score
from ..models import MetricResult
from .base import BaseMetric, MetricContext, register_metric


@register_metric
class AlignmentMetric(BaseMetric):
    name = "alignment"
    dimension = "consistency"

    def evaluate(self, context: MetricContext) -> MetricResult:
        eps = float(self.cfg(context).get("eps_px", 6))
        left_edges = [item.bbox.x for item in context.vision.elements]
        centers = [item.bbox.center[0] for item in context.vision.elements]
        ratio = (snap_ratio(left_edges, eps) + snap_ratio(centers, eps)) / 2
        return MetricResult(
            name=self.name,
            dimension=self.dimension,
            score=round(ratio * 100, 2),
            value=round(ratio, 4),
            ideal=1.0,
            deviation=round(1.0 - ratio, 4),
            formula="mean(x-edge snap ratio, x-center snap ratio)",
            confidence=context.vision.confidence,
        )


@register_metric
class TypographyRhythmMetric(BaseMetric):
    name = "typography_rhythm"
    dimension = "consistency"

    def evaluate(self, context: MetricContext) -> MetricResult:
        cfg = self.cfg(context)
        levels = {round(block.font_size / 2) * 2 for block in context.vision.text_blocks}
        if not levels:
            return MetricResult(
                name=self.name,
                dimension=self.dimension,
                score=0.0,
                value=0,
                ideal=float(cfg.get("levels_mean", 3)),
                deviation=float(cfg.get("levels_mean", 3)),
                formula="no text blocks -> score 0",
                confidence=0.0,
                details={"reason": "no OCR text found"},
            )
        count = len(levels)
        score = gaussian_score(count, float(cfg.get("levels_mean", 3)), float(cfg.get("levels_sigma", 1.5)))
        return MetricResult(
            name=self.name,
            dimension=self.dimension,
            score=round(score, 2),
            value=count,
            ideal=float(cfg.get("levels_mean", 3)),
            deviation=abs(count - float(cfg.get("levels_mean", 3))),
            formula="Gaussian(font_size_level_count)",
            confidence=context.vision.confidence,
            details={"levels": sorted(levels)},
        )


@register_metric
class ComponentSizeMetric(BaseMetric):
    name = "component_size"
    dimension = "consistency"

    def evaluate(self, context: MetricContext) -> MetricResult:
        cfg = self.cfg(context)
        areas = [item.bbox.area for item in context.vision.elements if item.kind == "component"]
        if len(areas) < 2:
            return MetricResult(
                name=self.name,
                dimension=self.dimension,
                score=None,
                value=len(areas),
                ideal=">=2 components",
                formula="insufficient component samples",
                confidence=0.0,
                status="skipped",
                details={"reason": "fewer than 2 detected components", "component_count": len(areas)},
            )
        cv = coefficient_of_variation(areas)
        k = float(cfg.get("cv_k", 2.5))
        score = 100 * np.exp(-k * cv)
        return MetricResult(
            name=self.name,
            dimension=self.dimension,
            score=round(float(score), 2),
            value=round(cv, 4),
            ideal=0.0,
            deviation=round(cv, 4),
            formula=f"100 * exp(-{k} * CV)",
            confidence=context.vision.confidence,
            details={"component_count": len(areas)},
        )


@register_metric
class CornerRadiusConsistencyMetric(BaseMetric):
    name = "corner_radius_consistency"
    dimension = "consistency"

    def evaluate(self, context: MetricContext) -> MetricResult:
        cfg = self.cfg(context)
        bucket_px = float(cfg.get("bucket_px", 2))
        values = [
            float(item.radius)
            for item in context.vision.elements
            if item.kind != "text" and item.radius is not None and item.radius >= 0
        ]
        if len(values) < 2:
            return MetricResult(
                name=self.name,
                dimension=self.dimension,
                score=None,
                value=len(values),
                ideal=">=2 radius samples",
                formula="insufficient radius samples",
                confidence=0.0,
                status="skipped",
                details={"reason": "fewer than 2 radius samples"},
            )
        buckets = {round(value / max(0.1, bucket_px)) * bucket_px for value in values}
        ideal_unique = float(cfg.get("ideal_unique", 2))
        penalty_k = float(cfg.get("penalty_k", 0.55))
        extra = max(0.0, len(buckets) - ideal_unique)
        score = 100 * np.exp(-penalty_k * extra)
        return MetricResult(
            name=self.name,
            dimension=self.dimension,
            score=round(float(score), 2),
            value={"unique_radius_count": len(buckets), "radii": [round(value, 2) for value in values]},
            ideal={"unique_radius_count": ideal_unique},
            deviation=extra,
            formula=f"100 * exp(-{penalty_k} * max(0, unique_radius_count - {ideal_unique}))",
            confidence=context.vision.confidence,
        )


@register_metric
class PaddingConsistencyMetric(BaseMetric):
    name = "padding_consistency"
    dimension = "consistency"

    def evaluate(self, context: MetricContext) -> MetricResult:
        cfg = self.cfg(context)
        values: list[float] = []
        component_count = 0
        for element in context.vision.elements:
            padding = element.style_features.get("padding")
            if isinstance(padding, list) and padding:
                component_count += 1
                values.extend(float(item) for item in padding if item is not None)
        if len(values) < 4:
            return MetricResult(
                name=self.name,
                dimension=self.dimension,
                score=None,
                value=component_count,
                ideal=">=1 component with text padding",
                formula="insufficient padding samples",
                confidence=0.0,
                status="skipped",
                details={"reason": "no component text padding samples"},
            )
        cv = coefficient_of_variation(values)
        k = float(cfg.get("cv_k", 3.0))
        score = 100 * np.exp(-k * cv)
        return MetricResult(
            name=self.name,
            dimension=self.dimension,
            score=round(float(score), 2),
            value=round(cv, 4),
            ideal=0.0,
            deviation=round(cv, 4),
            formula=f"100 * exp(-{k} * CV)",
            confidence=context.vision.confidence,
            details={"component_count": component_count, "padding_values": [round(value, 2) for value in values]},
        )


@register_metric
class IconSizeConsistencyMetric(BaseMetric):
    name = "icon_size_consistency"
    dimension = "consistency"

    def evaluate(self, context: MetricContext) -> MetricResult:
        cfg = self.cfg(context)
        sizes = [float(np.sqrt(item.bbox.area)) for item in context.vision.elements if item.kind == "icon"]
        if len(sizes) < 2:
            return MetricResult(
                name=self.name,
                dimension=self.dimension,
                score=None,
                value=len(sizes),
                ideal=">=2 icons",
                formula="insufficient icon samples",
                confidence=0.0,
                status="skipped",
                details={"reason": "fewer than 2 detected icons"},
            )
        cv = coefficient_of_variation(sizes)
        k = float(cfg.get("cv_k", 3.5))
        score = 100 * np.exp(-k * cv)
        return MetricResult(
            name=self.name,
            dimension=self.dimension,
            score=round(float(score), 2),
            value=round(cv, 4),
            ideal=0.0,
            deviation=round(cv, 4),
            formula=f"100 * exp(-{k} * CV)",
            confidence=context.vision.confidence,
            details={"icon_count": len(sizes), "sizes": [round(size, 2) for size in sizes]},
        )


@register_metric
class GridMetric(BaseMetric):
    name = "grid"
    dimension = "consistency"

    def evaluate(self, context: MetricContext) -> MetricResult:
        eps = float(self.cfg(context).get("eps_px", 6))
        x_values = [item.bbox.x for item in context.vision.elements] + [item.bbox.x2 for item in context.vision.elements]
        y_values = [item.bbox.y for item in context.vision.elements] + [item.bbox.y2 for item in context.vision.elements]
        ratio = (snap_ratio(x_values, eps) + snap_ratio(y_values, eps)) / 2
        return MetricResult(
            name=self.name,
            dimension=self.dimension,
            score=round(ratio * 100, 2),
            value=round(ratio, 4),
            ideal=1.0,
            deviation=round(1.0 - ratio, 4),
            formula="mean(x snap ratio, y snap ratio)",
            confidence=context.vision.confidence,
        )


@register_metric
class StyleSimplicityMetric(BaseMetric):
    name = "style_simplicity"
    dimension = "consistency"

    def evaluate(self, context: MetricContext) -> MetricResult:
        cfg = self.cfg(context)
        count = len(context.vision.dominant_colors)
        score = gaussian_score(count, float(cfg.get("color_count_mean", 4)), float(cfg.get("color_count_sigma", 2)))
        return MetricResult(
            name=self.name,
            dimension=self.dimension,
            score=round(score, 2),
            value=count,
            ideal=float(cfg.get("color_count_mean", 4)),
            deviation=abs(count - float(cfg.get("color_count_mean", 4))),
            formula="Gaussian(dominant_color_count)",
            confidence=context.vision.confidence,
        )


def snap_ratio(values: list[float], eps: float) -> float:
    if len(values) < 2:
        return 1.0 if values else 0.0
    sorted_values = sorted(values)
    snapped = 0
    for index, value in enumerate(sorted_values):
        before = index > 0 and abs(value - sorted_values[index - 1]) <= eps
        after = index + 1 < len(sorted_values) and abs(sorted_values[index + 1] - value) <= eps
        if before or after:
            snapped += 1
    return snapped / len(sorted_values)
