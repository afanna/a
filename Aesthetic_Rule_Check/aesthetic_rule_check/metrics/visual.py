from __future__ import annotations

import math

import cv2
import numpy as np

from ..math_utils import gaussian_score, gini, sigmoid_score
from ..models import MetricResult, VisualElement
from .base import BaseMetric, MetricContext, register_metric


@register_metric
class ColorHarmonyMetric(BaseMetric):
    name = "color_harmony"
    dimension = "visual"

    def evaluate(self, context: MetricContext) -> MetricResult:
        cfg = self.cfg(context)
        colors = context.vision.dominant_colors
        count = len(colors)
        count_score = gaussian_score(count, float(cfg.get("color_count_mean", 4)), float(cfg.get("color_count_sigma", 1.6)))
        lab_distance = average_lab_distance(colors)
        distance_score = gaussian_score(
            lab_distance,
            float(cfg.get("lab_distance_mean", 32)),
            float(cfg.get("lab_distance_sigma", 18)),
        )
        score = (count_score + distance_score) / 2
        return MetricResult(
            name=self.name,
            dimension=self.dimension,
            score=round(score, 2),
            value={"color_count": count, "avg_lab_distance": round(lab_distance, 2)},
            ideal={"color_count": cfg.get("color_count_mean", 4), "avg_lab_distance": cfg.get("lab_distance_mean", 32)},
            formula="mean(Gaussian(color_count), Gaussian(avg_lab_distance))",
            confidence=context.vision.confidence,
            details={"colors": colors, "proportions": context.vision.color_proportions},
        )


@register_metric
class ContrastMetric(BaseMetric):
    name = "contrast"
    dimension = "visual"

    def evaluate(self, context: MetricContext) -> MetricResult:
        cfg = self.cfg(context)
        ratios = [block.contrast_ratio for block in context.vision.text_blocks if block.contrast_ratio is not None]
        if not ratios:
            return MetricResult(
                name=self.name,
                dimension=self.dimension,
                score=0.0,
                value=None,
                ideal=float(cfg.get("target", 4.5)),
                deviation=float(cfg.get("target", 4.5)),
                formula="no text blocks -> score 0",
                confidence=0.0,
                details={"reason": "no OCR text found"},
            )
        value = min(float(item) for item in ratios)
        score = sigmoid_score(value, float(cfg.get("target", 4.5)), float(cfg.get("k", 1.2)))
        return MetricResult(
            name=self.name,
            dimension=self.dimension,
            score=round(score, 2),
            value=round(value, 3),
            ideal=float(cfg.get("target", 4.5)),
            deviation=round(max(0.0, float(cfg.get("target", 4.5)) - value), 3),
            formula="Sigmoid(min_contrast)",
            confidence=context.vision.confidence,
            details={"ratios": [round(float(item), 3) for item in ratios]},
        )


@register_metric
class VisualFocusMetric(BaseMetric):
    name = "visual_focus"
    dimension = "visual"

    def evaluate(self, context: MetricContext) -> MetricResult:
        cfg = self.cfg(context)
        if not context.vision.elements:
            return MetricResult(
                name=self.name,
                dimension=self.dimension,
                score=0.0,
                value=0.0,
                ideal=float(cfg.get("mean", 0.42)),
                deviation=float(cfg.get("mean", 0.42)),
                formula="no visual elements -> score 0",
                confidence=0.0,
                details={"reason": "no visual elements found"},
            )
        weights = [visual_weight(item, context) for item in context.vision.elements]
        total = sum(weights)
        focus = max(weights) / total if total > 0 else 0.0
        score = gaussian_score(focus, float(cfg.get("mean", 0.42)), float(cfg.get("sigma", 0.18)))
        return MetricResult(
            name=self.name,
            dimension=self.dimension,
            score=round(score, 2),
            value=round(focus, 4),
            ideal=float(cfg.get("mean", 0.42)),
            deviation=round(abs(focus - float(cfg.get("mean", 0.42))), 4),
            formula="Gaussian(max_visual_weight / sum_visual_weight)",
            confidence=context.vision.confidence,
        )


@register_metric
class VisualBalanceMetric(BaseMetric):
    name = "visual_balance"
    dimension = "visual"

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
        weights = [visual_weight(item, context) for item in context.vision.elements]
        total = sum(weights)
        cx = sum(item.bbox.center[0] * weight for item, weight in zip(context.vision.elements, weights)) / total
        cy = sum(item.bbox.center[1] * weight for item, weight in zip(context.vision.elements, weights)) / total
        dx = (cx - context.vision.width / 2) / max(1, context.vision.width)
        dy = (cy - context.vision.height / 2) / max(1, context.vision.height)
        offset = math.sqrt(dx * dx + dy * dy)
        score = gaussian_score(offset, 0.0, float(cfg.get("sigma", 0.28)))
        return MetricResult(
            name=self.name,
            dimension=self.dimension,
            score=round(score, 2),
            value=round(offset, 4),
            ideal=0.0,
            deviation=round(offset, 4),
            formula="Euclidean distance + Gaussian",
            confidence=context.vision.confidence,
        )


@register_metric
class TextImageRatioMetric(BaseMetric):
    name = "text_image_ratio"
    dimension = "visual"

    def evaluate(self, context: MetricContext) -> MetricResult:
        cfg = self.cfg(context)
        if not context.vision.text_blocks:
            return MetricResult(
                name=self.name,
                dimension=self.dimension,
                score=0.0,
                value=0.0,
                ideal=float(cfg.get("mean", 0.55)),
                deviation=float(cfg.get("mean", 0.55)),
                formula="no text blocks -> score 0",
                confidence=0.0,
                details={"reason": "no OCR text found"},
            )
        text_area = sum(block.bbox.area for block in context.vision.text_blocks)
        total_area = sum(item.bbox.area for item in context.vision.elements)
        ratio = text_area / total_area if total_area > 0 else 0.0
        score = gaussian_score(ratio, float(cfg.get("mean", 0.55)), float(cfg.get("sigma", 0.25)))
        return MetricResult(
            name=self.name,
            dimension=self.dimension,
            score=round(score, 2),
            value=round(ratio, 4),
            ideal=float(cfg.get("mean", 0.55)),
            deviation=round(abs(ratio - float(cfg.get("mean", 0.55))), 4),
            formula="Gaussian(text_area / occupied_area)",
            confidence=context.vision.confidence,
        )


@register_metric
class ReadingFlowMetric(BaseMetric):
    name = "reading_flow"
    dimension = "visual"

    def evaluate(self, context: MetricContext) -> MetricResult:
        blocks = sorted(context.vision.text_blocks, key=lambda item: (item.bbox.y, item.bbox.x))
        if not blocks:
            return MetricResult(
                name=self.name,
                dimension=self.dimension,
                score=0.0,
                value=0,
                ideal=">=3 text blocks",
                formula="no text blocks -> score 0",
                confidence=0.0,
                details={"reason": "no OCR text found"},
            )
        if len(blocks) < 3:
            return MetricResult(
                name=self.name,
                dimension=self.dimension,
                score=85.0,
                value=len(blocks),
                ideal=">=3 text blocks",
                formula="small text count fallback",
                confidence=context.vision.confidence,
            )
        centers = [block.bbox.center for block in blocks]
        diagonal = math.hypot(context.vision.width, context.vision.height)
        path = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(centers, centers[1:])) / max(1.0, diagonal)
        backtracks = sum(1 for a, b in zip(centers, centers[1:]) if b[1] + 4 < a[1])
        penalty = min(100.0, path * 18 + backtracks * 12)
        score = max(0.0, 100.0 - penalty)
        return MetricResult(
            name=self.name,
            dimension=self.dimension,
            score=round(score, 2),
            value={"path_norm": round(path, 4), "backtracks": backtracks},
            ideal={"path_norm": "low", "backtracks": 0},
            formula="100 - path_penalty - backtrack_penalty",
            confidence=context.vision.confidence,
        )


@register_metric
class HierarchyMetric(BaseMetric):
    name = "hierarchy"
    dimension = "visual"

    def evaluate(self, context: MetricContext) -> MetricResult:
        cfg = self.cfg(context)
        if not context.vision.text_blocks:
            return MetricResult(
                name=self.name,
                dimension=self.dimension,
                score=0.0,
                value=0.0,
                ideal=float(cfg.get("mean", 0.35)),
                deviation=float(cfg.get("mean", 0.35)),
                formula="no text blocks -> score 0",
                confidence=0.0,
                details={"reason": "no OCR text found"},
            )
        values = [block.font_size * max(1.0, block.bbox.width) for block in context.vision.text_blocks]
        hierarchy = gini(values)
        score = gaussian_score(hierarchy, float(cfg.get("mean", 0.35)), float(cfg.get("sigma", 0.16)))
        return MetricResult(
            name=self.name,
            dimension=self.dimension,
            score=round(score, 2),
            value=round(hierarchy, 4),
            ideal=float(cfg.get("mean", 0.35)),
            deviation=round(abs(hierarchy - float(cfg.get("mean", 0.35))), 4),
            formula="Gaussian(Gini(text_visual_weight))",
            confidence=context.vision.confidence,
        )


def visual_weight(element: VisualElement, context: MetricContext | None = None) -> float:
    section = context.config.section("visual") if context is not None else {}
    kind_weights = section.get("element_weights", {}) if isinstance(section.get("element_weights", {}), dict) else {}
    kind_factor = float(
        kind_weights.get(
            element.kind,
            {
                "text": 1.2,
                "icon": 1.15,
                "image": 1.0,
                "button": 1.1,
                "tag": 0.95,
                "component": 0.8,
            }.get(element.kind, 1.0),
        )
    )
    base = max(1.0, element.bbox.area)
    if element.kind == "text":
        contrast = element.style_features.get("contrast_ratio")
        font_size = float(element.style_features.get("font_size") or element.bbox.height)
        contrast_target = float(section.get("visual_weight_contrast_target", 4.5))
        font_reference = float(section.get("visual_weight_font_reference", 16))
        contrast_factor = max(0.5, min(2.0, float(contrast or contrast_target) / max(0.1, contrast_target)))
        font_factor = max(0.6, min(2.0, font_size / max(1.0, font_reference)))
        return base * kind_factor * contrast_factor * font_factor
    return base * kind_factor


def average_lab_distance(colors: list[tuple[int, int, int]]) -> float:
    if len(colors) < 2:
        return 0.0
    rgb = np.array(colors, dtype=np.uint8).reshape(-1, 1, 3)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
    distances: list[float] = []
    for index, left in enumerate(lab):
        for right in lab[index + 1 :]:
            distances.append(float(np.linalg.norm(left - right)))
    return sum(distances) / len(distances) if distances else 0.0
