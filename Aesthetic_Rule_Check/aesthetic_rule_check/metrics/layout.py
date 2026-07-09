from __future__ import annotations

import numpy as np

from ..math_utils import coefficient_of_variation, gaussian_score, rect_contains, rect_iou
from ..models import MetricResult, Rect, VisualElement
from .base import BaseMetric, MetricContext, register_metric


def occupied_mask_ratio(context: MetricContext) -> float:
    mask = np.zeros((context.vision.height, context.vision.width), dtype=np.uint8)
    for element in context.vision.elements:
        x1 = max(0, int(element.bbox.x))
        y1 = max(0, int(element.bbox.y))
        x2 = min(context.vision.width, int(element.bbox.x2))
        y2 = min(context.vision.height, int(element.bbox.y2))
        if x2 > x1 and y2 > y1:
            mask[y1:y2, x1:x2] = 1
    return float(mask.mean())


def vertical_gaps(elements: list[VisualElement]) -> list[float]:
    ordered = sorted(elements, key=lambda item: item.bbox.y)
    gaps: list[float] = []
    for prev, current in zip(ordered, ordered[1:]):
        gap = current.bbox.y - prev.bbox.y2
        if gap > 0:
            gaps.append(gap)
    return gaps


@register_metric
class WhitespaceMetric(BaseMetric):
    name = "whitespace"
    dimension = "layout"

    def evaluate(self, context: MetricContext) -> MetricResult:
        cfg = self.cfg(context)
        occupied = occupied_mask_ratio(context)
        whitespace = 1.0 - occupied
        mean = float(cfg.get("mean", 0.45))
        sigma = float(cfg.get("sigma", 0.16))
        score = gaussian_score(whitespace, mean, sigma)
        return MetricResult(
            name=self.name,
            dimension=self.dimension,
            score=round(score, 2),
            value=round(whitespace, 4),
            ideal=mean,
            deviation=round(abs(whitespace - mean), 4),
            formula="Gaussian",
            confidence=context.vision.confidence,
        )


@register_metric
class MarginConsistencyMetric(BaseMetric):
    name = "margin_consistency"
    dimension = "layout"

    def evaluate(self, context: MetricContext) -> MetricResult:
        cfg = self.cfg(context)
        if not context.vision.elements:
            return MetricResult(
                name=self.name,
                dimension=self.dimension,
                score=0.0,
                value=None,
                ideal=0.0,
                formula="no visual elements -> score 0",
                confidence=0.0,
                details={"reason": "no visual elements found"},
            )
        distances: list[float] = []
        for element in context.vision.elements:
            distances.extend(
                [
                    element.bbox.x,
                    context.vision.width - element.bbox.x2,
                    element.bbox.y,
                    context.vision.height - element.bbox.y2,
                ]
            )
        cv = coefficient_of_variation([value for value in distances if value >= 0])
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
        )


@register_metric
class SpacingRhythmMetric(BaseMetric):
    name = "spacing_rhythm"
    dimension = "layout"

    def evaluate(self, context: MetricContext) -> MetricResult:
        cfg = self.cfg(context)
        gaps = vertical_gaps(context.vision.elements)
        if len(gaps) < 2:
            return MetricResult(
                name=self.name,
                dimension=self.dimension,
                score=None,
                value=len(gaps),
                ideal=">=2 gaps",
                formula="insufficient spacing samples",
                confidence=0.0,
                status="skipped",
                details={"reason": "fewer than 2 vertical gaps", "gap_count": len(gaps)},
            )
        cv = coefficient_of_variation(gaps)
        k = float(cfg.get("cv_k", 4.0))
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
            details={"gap_count": len(gaps)},
        )


@register_metric
class DensityMetric(BaseMetric):
    name = "density"
    dimension = "layout"

    def evaluate(self, context: MetricContext) -> MetricResult:
        cfg = self.cfg(context)
        density = occupied_mask_ratio(context)
        mean = float(cfg.get("mean", 0.55))
        sigma = float(cfg.get("sigma", 0.16))
        score = gaussian_score(density, mean, sigma)
        return MetricResult(
            name=self.name,
            dimension=self.dimension,
            score=round(score, 2),
            value=round(density, 4),
            ideal=mean,
            deviation=round(abs(density - mean), 4),
            formula="Gaussian",
            confidence=context.vision.confidence,
        )


@register_metric
class OverlapMetric(BaseMetric):
    name = "overlap"
    dimension = "layout"

    def evaluate(self, context: MetricContext) -> MetricResult:
        cfg = self.cfg(context)
        max_iou = 0.0
        pairs: list[dict[str, float | str]] = []
        elements = context.vision.elements
        if len(elements) < 2:
            return MetricResult(
                name=self.name,
                dimension=self.dimension,
                score=None,
                value=len(elements),
                ideal=">=2 elements",
                formula="insufficient overlap samples",
                confidence=0.0,
                status="skipped",
                details={"reason": "fewer than 2 visual elements"},
            )
        for index, left in enumerate(elements):
            for right in elements[index + 1 :]:
                if is_allowed_containment(left.bbox, right.bbox):
                    continue
                iou = rect_iou(left.bbox, right.bbox)
                if iou > max_iou:
                    max_iou = iou
                if iou > 0.02:
                    pairs.append({"left": left.kind, "right": right.kind, "iou": round(iou, 4)})
        k = float(cfg.get("penalty_k", 100))
        score = max(0.0, 100.0 - k * max_iou)
        return MetricResult(
            name=self.name,
            dimension=self.dimension,
            score=round(score, 2),
            value=round(max_iou, 4),
            ideal=0.0,
            deviation=round(max_iou, 4),
            formula=f"max(0, 100 - {k} * max_iou)",
            confidence=context.vision.confidence,
            details={"pairs": pairs[:20]},
        )


@register_metric
class OverflowMetric(BaseMetric):
    name = "overflow"
    dimension = "layout"

    def evaluate(self, context: MetricContext) -> MetricResult:
        cfg = self.cfg(context)
        if not context.vision.elements:
            return MetricResult(
                name=self.name,
                dimension=self.dimension,
                score=None,
                value=0,
                ideal=">=1 element",
                formula="insufficient overflow samples",
                confidence=0.0,
                status="skipped",
                details={"reason": "no visual elements found"},
            )
        card = Rect(0, 0, context.vision.width, context.vision.height)
        outside_area = 0.0
        total_area = 0.0
        for element in context.vision.elements:
            total_area += element.bbox.area
            inside_width = max(0.0, min(card.x2, element.bbox.x2) - max(card.x, element.bbox.x))
            inside_height = max(0.0, min(card.y2, element.bbox.y2) - max(card.y, element.bbox.y))
            outside_area += max(0.0, element.bbox.area - inside_width * inside_height)
        overflow = outside_area / total_area if total_area > 0 else 0.0
        k = float(cfg.get("penalty_k", 100))
        score = max(0.0, 100.0 - k * overflow)
        return MetricResult(
            name=self.name,
            dimension=self.dimension,
            score=round(score, 2),
            value=round(overflow, 4),
            ideal=0.0,
            deviation=round(overflow, 4),
            formula=f"max(0, 100 - {k} * overflow)",
            confidence=context.vision.confidence,
        )


def is_allowed_containment(left: Rect, right: Rect) -> bool:
    return rect_contains(left, right, tolerance=2) or rect_contains(right, left, tolerance=2)
