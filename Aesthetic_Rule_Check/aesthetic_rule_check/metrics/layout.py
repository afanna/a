from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from ..math_utils import clamp, coefficient_of_variation, gaussian_score, rect_contains, rect_iou
from ..models import MetricResult, Rect, VisualElement
from .base import BaseMetric, MetricContext, register_metric


def element_occupied_mask_ratio(context: MetricContext) -> float:
    mask = np.zeros((context.vision.height, context.vision.width), dtype=np.uint8)
    for element in context.vision.elements:
        x1 = max(0, int(element.bbox.x))
        y1 = max(0, int(element.bbox.y))
        x2 = min(context.vision.width, int(element.bbox.x2))
        y2 = min(context.vision.height, int(element.bbox.y2))
        if x2 > x1 and y2 > y1:
            mask[y1:y2, x1:x2] = 1
    return float(mask.mean())


def pixel_foreground_ratio(context: MetricContext, cfg: dict | None = None) -> float | None:
    cfg = cfg or {}
    if not bool(cfg.get("pixel_foreground_enabled", True)):
        return None
    image_path = Path(context.vision.image_path)
    if not image_path.exists():
        return None
    data = np.fromfile(str(image_path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        return None
    height, width = image.shape[:2]
    border_px = max(1, int(min(width, height) * float(cfg.get("background_border_ratio", 0.05))))
    border = np.concatenate(
        [
            image[:border_px, :, :].reshape(-1, 3),
            image[-border_px:, :, :].reshape(-1, 3),
            image[:, :border_px, :].reshape(-1, 3),
            image[:, -border_px:, :].reshape(-1, 3),
        ],
        axis=0,
    )
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB).astype(np.float32)
    bg_lab = cv2.cvtColor(np.median(border, axis=0).reshape(1, 1, 3).astype(np.uint8), cv2.COLOR_BGR2LAB).astype(
        np.float32
    )[0, 0]
    distance = np.linalg.norm(lab - bg_lab, axis=2)
    threshold = float(cfg.get("pixel_foreground_lab_threshold", 35))
    mask = (distance > threshold).astype(np.uint8)
    kernel_size = int(cfg.get("pixel_foreground_open_kernel", 2))
    if kernel_size > 1:
        kernel = np.ones((kernel_size, kernel_size), dtype=np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    return float(mask.mean())


def occupied_mask_ratio(context: MetricContext, cfg: dict | None = None) -> float:
    element_ratio = element_occupied_mask_ratio(context)
    pixel_ratio = pixel_foreground_ratio(context, cfg)
    if pixel_ratio is None:
        return element_ratio
    return max(element_ratio, pixel_ratio)


def occupied_ratio_details(context: MetricContext, cfg: dict | None = None) -> dict[str, float | None]:
    element_ratio = element_occupied_mask_ratio(context)
    pixel_ratio = pixel_foreground_ratio(context, cfg)
    combined = max(element_ratio, pixel_ratio) if pixel_ratio is not None else element_ratio
    return {
        "element_occupied_ratio": round(element_ratio, 4),
        "pixel_foreground_ratio": round(pixel_ratio, 4) if pixel_ratio is not None else None,
        "combined_occupied_ratio": round(combined, 4),
    }


def band_score(value: float, lower: float, upper: float, sigma_low: float, sigma_high: float) -> float:
    if lower <= value <= upper:
        return 100.0
    if value < lower:
        return gaussian_score(value, lower, sigma_low)
    return gaussian_score(value, upper, sigma_high)


def configured_density_score(value: float, cfg: dict) -> tuple[float, str, object, float]:
    if "min" in cfg and "max" in cfg:
        lower = float(cfg.get("min", 0.0))
        upper = float(cfg.get("max", 1.0))
        sigma_low = float(cfg.get("sigma_low", cfg.get("sigma", 0.16)))
        sigma_high = float(cfg.get("sigma_high", cfg.get("sigma", 0.16)))
        score = band_score(value, lower, upper, sigma_low, sigma_high)
        if lower <= value <= upper:
            deviation = 0.0
        else:
            deviation = min(abs(value - lower), abs(value - upper))
        return score, "BandGaussian", {"min": lower, "max": upper}, deviation
    mean = float(cfg.get("mean", 0.55))
    sigma = float(cfg.get("sigma", 0.16))
    return gaussian_score(value, mean, sigma), "Gaussian", mean, abs(value - mean)


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
        occupied = occupied_mask_ratio(context, cfg)
        whitespace = 1.0 - occupied
        score, formula, ideal, deviation = configured_density_score(whitespace, cfg)
        return MetricResult(
            name=self.name,
            dimension=self.dimension,
            score=round(score, 2),
            value=round(whitespace, 4),
            ideal=ideal,
            deviation=round(deviation, 4),
            formula=formula,
            confidence=context.vision.confidence,
            details=occupied_ratio_details(context, cfg),
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
        density = occupied_mask_ratio(context, cfg)
        score, formula, ideal, deviation = configured_density_score(density, cfg)
        return MetricResult(
            name=self.name,
            dimension=self.dimension,
            score=round(score, 2),
            value=round(density, 4),
            ideal=ideal,
            deviation=round(deviation, 4),
            formula=formula,
            confidence=context.vision.confidence,
            details=occupied_ratio_details(context, cfg),
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
        deductions = overlap_deductions(max_iou, pairs, cfg)
        return MetricResult(
            name=self.name,
            dimension=self.dimension,
            score=round(score, 2),
            value=round(max_iou, 4),
            ideal=0.0,
            deviation=round(max_iou, 4),
            formula=f"max(0, 100 - {k} * max_iou)",
            confidence=context.vision.confidence,
            details={"pairs": pairs[:20], "deductions": deductions},
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


def overlap_deductions(max_iou: float, pairs: list[dict[str, float | str]], cfg: dict) -> list[dict]:
    if not pairs:
        return []
    warning_iou = float(cfg.get("deduction_iou", 0.08))
    hard_iou = float(cfg.get("hard_iou", 0.2))
    critical_kinds = {"text", "button"}
    important_pairs = [
        item
        for item in pairs
        if float(item.get("iou", 0.0)) >= warning_iou
        and (str(item.get("left")) in critical_kinds or str(item.get("right")) in critical_kinds)
    ]
    severe_pairs = [
        item
        for item in pairs
        if float(item.get("iou", 0.0)) >= hard_iou
        or (float(item.get("iou", 0.0)) >= warning_iou and str(item.get("left")) == str(item.get("right")) == "button")
    ]
    if max_iou < warning_iou and not important_pairs:
        return []
    severity = "high" if severe_pairs else "medium"
    top_pairs = sorted(pairs, key=lambda item: float(item.get("iou", 0.0)), reverse=True)[:3]
    evidence_pairs = ", ".join(
        f"{item.get('left')}-{item.get('right')} iou={float(item.get('iou', 0.0)):.4f}" for item in top_pairs
    )
    return [
        {
            "code": "layout.overlap",
            "source": "screenshot",
            "severity": severity,
            "score_delta": -round(max(6.0, max_iou * 100.0), 2),
            "evidence": f"max_iou={max_iou:.4f}; pairs={evidence_pairs}",
            "magnitude": clamp(max_iou / 0.25, 0.0, 1.0),
        }
    ]
