from __future__ import annotations

import math

import numpy as np

from ..math_utils import clamp, coefficient_of_variation, gaussian_score, rect_contains, rect_iou
from ..models import DslComponentBox, MetricResult, Rect
from .base import BaseMetric, MetricContext, register_metric


def card_rect(context: MetricContext) -> Rect:
    width = context.dsl.surface_width or context.vision.width or 160.0
    height = context.dsl.surface_height or context.vision.height or 160.0
    return Rect(0.0, 0.0, float(width), float(height))


def visible_boxes(context: MetricContext) -> list[DslComponentBox]:
    root_id = context.dsl.root_id
    return [box for box in context.dsl.geometry_boxes if box.component_id != root_id and is_visible_box(box)]


def is_visible_box(box: DslComponentBox) -> bool:
    styles = box.styles
    if box.text:
        return True
    if box.component_type in {"image", "button", "divider", "progress", "checkbox", "toggle", "radio"}:
        return True
    return any(key in styles for key in ("backgroundColor", "linearGradient", "borderWidth", "borderColor", "shadow"))


def rect_union_area(rects: list[Rect]) -> float:
    if not rects:
        return 0.0
    xs = sorted({value for rect in rects for value in (rect.x, rect.x2)})
    ys = sorted({value for rect in rects for value in (rect.y, rect.y2)})
    area = 0.0
    for left, right in zip(xs, xs[1:]):
        if right <= left:
            continue
        for top, bottom in zip(ys, ys[1:]):
            if bottom <= top:
                continue
            if any(rect.x < right and rect.x2 > left and rect.y < bottom and rect.y2 > top for rect in rects):
                area += (right - left) * (bottom - top)
    return area


def density_value(context: MetricContext) -> tuple[float, list[DslComponentBox]]:
    boxes = visible_boxes(context)
    card = card_rect(context)
    clipped = [clip_rect(box.bbox, card) for box in boxes]
    area = rect_union_area([rect for rect in clipped if rect.area > 0])
    return (area / card.area if card.area > 0 else 0.0), boxes


def clip_rect(rect: Rect, bounds: Rect) -> Rect:
    x1 = max(rect.x, bounds.x)
    y1 = max(rect.y, bounds.y)
    x2 = min(rect.x2, bounds.x2)
    y2 = min(rect.y2, bounds.y2)
    return Rect(x1, y1, max(0.0, x2 - x1), max(0.0, y2 - y1))


def density_score(value: float, cfg: dict) -> tuple[float, str, object, float]:
    lower = float(cfg.get("min", 0.20))
    upper = float(cfg.get("max", 0.78))
    sigma_low = float(cfg.get("sigma_low", 0.12))
    sigma_high = float(cfg.get("sigma_high", 0.18))
    if lower <= value <= upper:
        return 100.0, "BandGaussian", {"min": lower, "max": upper}, 0.0
    if value < lower:
        return gaussian_score(value, lower, sigma_low), "BandGaussian", {"min": lower, "max": upper}, lower - value
    return gaussian_score(value, upper, sigma_high), "BandGaussian", {"min": lower, "max": upper}, value - upper


def deduction(
    code: str,
    severity: str,
    delta: float,
    evidence: str,
    component_ids: list[str] | None = None,
    magnitude: float | None = None,
) -> dict:
    record = {
        "code": code,
        "source": "dsl",
        "severity": severity,
        "score_delta": -abs(float(delta)),
        "component_ids": component_ids or [],
        "evidence": evidence,
    }
    if magnitude is not None:
        record["magnitude"] = round(clamp(float(magnitude), 0.0, 1.0), 4)
    return record


@register_metric
class DslWhitespaceMetric(BaseMetric):
    name = "whitespace"
    dimension = "geometry"

    def evaluate(self, context: MetricContext) -> MetricResult:
        cfg = self.cfg(context)
        density, boxes = density_value(context)
        whitespace = 1.0 - density
        score, formula, ideal, deviation = density_score(whitespace, cfg)
        deductions = []
        min_value = float(cfg.get("min", 0.18))
        max_value = float(cfg.get("max", 0.72))
        if whitespace < min_value:
            deductions.append(deduction("geometry.density_too_high", "medium", 100 - score, f"whitespace={whitespace:.3f}, min={min_value:.3f}"))
        elif whitespace > max_value:
            deductions.append(deduction("geometry.density_too_low", "low", 100 - score, f"whitespace={whitespace:.3f}, max={max_value:.3f}"))
        return MetricResult(
            name=self.name,
            dimension=self.dimension,
            score=round(score, 2),
            value=round(whitespace, 4),
            ideal=ideal,
            deviation=round(deviation, 4),
            formula=formula,
            details={"visible_box_count": len(boxes), "deductions": deductions},
        )


@register_metric
class DslDensityMetric(BaseMetric):
    name = "density"
    dimension = "geometry"

    def evaluate(self, context: MetricContext) -> MetricResult:
        cfg = self.cfg(context)
        density, boxes = density_value(context)
        score, formula, ideal, deviation = density_score(density, cfg)
        deductions = []
        min_value = float(cfg.get("min", 0.28))
        max_value = float(cfg.get("max", 0.82))
        if density > max_value:
            deductions.append(deduction("geometry.density_too_high", "medium", 100 - score, f"density={density:.3f}, max={max_value:.3f}"))
        elif density < min_value:
            deductions.append(deduction("geometry.density_too_low", "low", 100 - score, f"density={density:.3f}, min={min_value:.3f}"))
        return MetricResult(
            name=self.name,
            dimension=self.dimension,
            score=round(score, 2),
            value=round(density, 4),
            ideal=ideal,
            deviation=round(deviation, 4),
            formula=formula,
            details={"visible_box_count": len(boxes), "deductions": deductions},
        )


@register_metric
class DslPaddingMetric(BaseMetric):
    name = "padding"
    dimension = "geometry"

    def evaluate(self, context: MetricContext) -> MetricResult:
        cfg = self.cfg(context)
        boxes = visible_boxes(context)
        if not boxes:
            return MetricResult(name=self.name, dimension=self.dimension, score=None, value=0, status="skipped", formula="no DSL boxes", details={"reason": "no DSL geometry boxes"})
        card = card_rect(context)
        left = min(box.bbox.x for box in boxes)
        top = min(box.bbox.y for box in boxes)
        right = min(card.x2 - box.bbox.x2 for box in boxes)
        bottom = min(card.y2 - box.bbox.y2 for box in boxes)
        values = [left, right, top, bottom]
        cv = coefficient_of_variation(max(0.0, value) for value in values)
        k = float(cfg.get("cv_k", 2.2))
        score = 100.0 * math.exp(-k * cv)
        safe_padding = float(cfg.get("safe_padding", 8.0))
        deductions = []
        too_close = [name for name, value in zip(("left", "right", "top", "bottom"), values) if value < safe_padding]
        if too_close:
            deductions.append(deduction("geometry.edge_too_close", "medium", max(4.0, 100.0 - score), f"padding={dict(zip(('left','right','top','bottom'), [round(v, 2) for v in values]))}, safe_padding={safe_padding}"))
        return MetricResult(
            name=self.name,
            dimension=self.dimension,
            score=round(float(score), 2),
            value={"left": round(left, 2), "right": round(right, 2), "top": round(top, 2), "bottom": round(bottom, 2), "cv": round(cv, 4)},
            ideal={"safe_padding": safe_padding, "cv": 0.0},
            deviation=round(cv, 4),
            formula=f"100 * exp(-{k} * CV(edge padding))",
            details={"deductions": deductions},
        )


@register_metric
class DslAlignmentMetric(BaseMetric):
    name = "alignment"
    dimension = "geometry"

    def evaluate(self, context: MetricContext) -> MetricResult:
        cfg = self.cfg(context)
        boxes = visible_boxes(context)
        eps = float(cfg.get("eps", 2.0))
        left_edges = [box.bbox.x for box in boxes]
        centers = [box.bbox.center[0] for box in boxes]
        ratio = (snap_ratio(left_edges, eps) + snap_ratio(centers, eps)) / 2
        score = ratio * 100.0
        deductions = []
        if len(boxes) >= 3 and ratio < float(cfg.get("min_ratio", 0.45)):
            deductions.append(deduction("geometry.alignment_weak", "low", 100.0 - score, f"snap_ratio={ratio:.3f}, eps={eps}"))
        return MetricResult(
            name=self.name,
            dimension=self.dimension,
            score=round(score, 2),
            value=round(ratio, 4),
            ideal=1.0,
            deviation=round(1.0 - ratio, 4),
            formula="mean(left edge snap ratio, center snap ratio)",
            details={"box_count": len(boxes), "deductions": deductions},
        )


@register_metric
class DslGridMetric(BaseMetric):
    name = "grid"
    dimension = "geometry"

    def evaluate(self, context: MetricContext) -> MetricResult:
        cfg = self.cfg(context)
        boxes = visible_boxes(context)
        candidates = cfg.get("candidates", [4, 8, 12, 16])
        eps = float(cfg.get("eps", 2.0))
        values = [value for box in boxes for value in (box.bbox.x, box.bbox.y, box.bbox.x2, box.bbox.y2)]
        best_grid = None
        best_ratio = 0.0
        for grid in candidates if isinstance(candidates, list) else [4, 8, 12, 16]:
            grid_size = float(grid)
            if grid_size <= 0:
                continue
            ratio = grid_snap_ratio(values, grid_size, eps)
            if ratio > best_ratio:
                best_ratio = ratio
                best_grid = grid_size
        deductions = []
        if values and best_ratio < float(cfg.get("min_ratio", 0.45)):
            deductions.append(deduction("geometry.grid_weak", "low", 100.0 - best_ratio * 100.0, f"best_grid={best_grid}, snap_ratio={best_ratio:.3f}, eps={eps}"))
        return MetricResult(
            name=self.name,
            dimension=self.dimension,
            score=round(best_ratio * 100.0, 2),
            value={"best_grid": best_grid, "snap_ratio": round(best_ratio, 4)},
            ideal=1.0,
            deviation=round(1.0 - best_ratio, 4),
            formula="max grid snap ratio over candidate grids",
            details={"candidate_grids": candidates, "deductions": deductions},
        )


@register_metric
class DslOverlapMetric(BaseMetric):
    name = "overlap"
    dimension = "geometry"

    def evaluate(self, context: MetricContext) -> MetricResult:
        cfg = self.cfg(context)
        boxes = visible_boxes(context)
        if len(boxes) < 2:
            return MetricResult(name=self.name, dimension=self.dimension, score=None, value=len(boxes), status="skipped", formula="fewer than 2 boxes", details={"reason": "fewer than 2 DSL geometry boxes"})
        max_iou = 0.0
        pairs: list[dict] = []
        for index, left in enumerate(boxes):
            for right in boxes[index + 1 :]:
                if rect_contains(left.bbox, right.bbox, tolerance=1.0) or rect_contains(right.bbox, left.bbox, tolerance=1.0):
                    continue
                iou = rect_iou(left.bbox, right.bbox)
                if iou > max_iou:
                    max_iou = iou
                if iou > float(cfg.get("report_threshold", 0.02)):
                    pairs.append({"left": left.component_id, "right": right.component_id, "iou": round(iou, 4)})
        k = float(cfg.get("penalty_k", 180.0))
        score = max(0.0, 100.0 - k * max_iou)
        deductions = []
        if pairs and max_iou >= float(cfg.get("deduct_threshold", 0.04)):
            severity = "high" if max_iou >= 0.12 else "medium"
            component_ids = [pairs[0]["left"], pairs[0]["right"]]
            # 重叠幅度 = clamp(max_iou / 0.25, 0, 1)，IoU 达到 0.25 视为最严重。
            deductions.append(
                deduction(
                    "geometry.overlap",
                    severity,
                    100.0 - score,
                    f"max_iou={max_iou:.4f}",
                    component_ids,
                    magnitude=clamp(max_iou / 0.25, 0.0, 1.0),
                )
            )
        return MetricResult(
            name=self.name,
            dimension=self.dimension,
            score=round(score, 2),
            value=round(max_iou, 4),
            ideal=0.0,
            deviation=round(max_iou, 4),
            formula=f"max(0, 100 - {k} * max_iou)",
            details={"pairs": pairs[:20], "deductions": deductions},
        )


@register_metric
class DslSpacingRhythmMetric(BaseMetric):
    name = "spacing_rhythm"
    dimension = "geometry"

    def evaluate(self, context: MetricContext) -> MetricResult:
        cfg = self.cfg(context)
        boxes = sorted(visible_boxes(context), key=lambda box: (box.bbox.y, box.bbox.x))
        gaps: list[float] = []
        for prev, current in zip(boxes, boxes[1:]):
            gap = current.bbox.y - prev.bbox.y2
            if gap > 0:
                gaps.append(gap)
        if len(gaps) < 2:
            return MetricResult(name=self.name, dimension=self.dimension, score=None, value=len(gaps), status="skipped", formula="fewer than 2 vertical gaps", details={"reason": "fewer than 2 vertical gaps"})
        cv = coefficient_of_variation(gaps)
        k = float(cfg.get("cv_k", 2.4))
        score = 100.0 * math.exp(-k * cv)
        deductions = []
        if cv > float(cfg.get("max_cv", 0.9)):
            deductions.append(deduction("geometry.rhythm_weak", "low", 100.0 - score, f"gap_cv={cv:.3f}, gaps={[round(g, 2) for g in gaps[:12]]}"))
        return MetricResult(
            name=self.name,
            dimension=self.dimension,
            score=round(float(score), 2),
            value=round(cv, 4),
            ideal=0.0,
            deviation=round(cv, 4),
            formula=f"100 * exp(-{k} * CV(vertical gaps))",
            details={"gap_count": len(gaps), "gaps": [round(gap, 2) for gap in gaps[:20]], "deductions": deductions},
        )


@register_metric
class DslTypographyHierarchyMetric(BaseMetric):
    name = "typography_hierarchy"
    dimension = "geometry"

    def evaluate(self, context: MetricContext) -> MetricResult:
        cfg = self.cfg(context)
        font_sizes = [float(box.font_size) for box in visible_boxes(context) if box.font_size is not None and box.text]
        if not font_sizes:
            return MetricResult(name=self.name, dimension=self.dimension, score=None, value=0, status="skipped", formula="no DSL font sizes", details={"reason": "no DSL text font sizes"})
        levels = sorted({round(value / 2.0) * 2.0 for value in font_sizes})
        level_count = len(levels)
        level_score = gaussian_score(level_count, float(cfg.get("levels_mean", 3)), float(cfg.get("levels_sigma", 1.4)))
        ratio = max(font_sizes) / max(min(font_sizes), 1.0)
        ratio_score = gaussian_score(ratio, float(cfg.get("ratio_mean", 1.65)), float(cfg.get("ratio_sigma", 0.65)))
        score = (level_score + ratio_score) / 2
        deductions = []
        if level_count <= 1 and len(font_sizes) >= 3:
            deductions.append(deduction("geometry.hierarchy_weak", "medium", 100.0 - score, f"font_levels={levels}, ratio={ratio:.2f}"))
        elif level_count > int(cfg.get("max_levels", 5)):
            deductions.append(deduction("geometry.typography_too_fragmented", "low", 100.0 - score, f"font_levels={levels}"))
        return MetricResult(
            name=self.name,
            dimension=self.dimension,
            score=round(score, 2),
            value={"level_count": level_count, "levels": levels, "ratio": round(ratio, 3)},
            ideal={"level_count": cfg.get("levels_mean", 3), "ratio": cfg.get("ratio_mean", 1.65)},
            deviation={"level_count": abs(level_count - float(cfg.get("levels_mean", 3))), "ratio": round(abs(ratio - float(cfg.get("ratio_mean", 1.65))), 3)},
            formula="mean(Gaussian(font level count), Gaussian(max/min font ratio))",
            details={"deductions": deductions},
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


def grid_snap_ratio(values: list[float], grid: float, eps: float) -> float:
    if not values:
        return 0.0
    snapped = 0
    for value in values:
        remainder = abs(value) % grid
        distance = min(remainder, grid - remainder)
        if distance <= eps:
            snapped += 1
    return snapped / len(values)
