from __future__ import annotations

import math
import re
from difflib import SequenceMatcher
from typing import Any, Iterable

from .models import Rect


def clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    if math.isnan(value) or math.isinf(value):
        return lower
    return max(lower, min(upper, value))


def gaussian_score(value: float, mean: float, sigma: float) -> float:
    if sigma <= 0:
        return 0.0
    return clamp(100.0 * math.exp(-((value - mean) ** 2) / (2 * sigma * sigma)))


def sigmoid_score(value: float, target: float, k: float) -> float:
    try:
        return clamp(100.0 / (1.0 + math.exp(-k * (value - target))))
    except OverflowError:
        return 0.0 if value < target else 100.0


def coefficient_of_variation(values: Iterable[float]) -> float:
    items = [float(v) for v in values if v is not None]
    if len(items) < 2:
        return 0.0
    mean = sum(items) / len(items)
    if abs(mean) < 1e-9:
        return 0.0
    variance = sum((value - mean) ** 2 for value in items) / len(items)
    return abs(math.sqrt(variance) / mean)


def weighted_average(items: Iterable[tuple[float, float]]) -> float:
    pairs = [(float(score), float(weight)) for score, weight in items if weight > 0]
    total_weight = sum(weight for _, weight in pairs)
    if total_weight <= 0:
        return 0.0
    return clamp(sum(score * weight for score, weight in pairs) / total_weight)


def rect_iou(a: Rect, b: Rect) -> float:
    x1 = max(a.x, b.x)
    y1 = max(a.y, b.y)
    x2 = min(a.x2, b.x2)
    y2 = min(a.y2, b.y2)
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = a.area + b.area - intersection
    return intersection / union if union > 0 else 0.0


def rect_contains(outer: Rect, inner: Rect, tolerance: float = 1.0) -> bool:
    return (
        inner.x >= outer.x - tolerance
        and inner.y >= outer.y - tolerance
        and inner.x2 <= outer.x2 + tolerance
        and inner.y2 <= outer.y2 + tolerance
    )


def normalize_text(text: str) -> str:
    text = str(text or "").strip().lower()
    return re.sub(r"[\s,，。.!！?？:：;；·\-_/\\|]+", "", text)


def text_similarity(left: str, right: str) -> float:
    a = normalize_text(left)
    b = normalize_text(right)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return min(len(a), len(b)) / max(len(a), len(b))
    return SequenceMatcher(None, a, b).ratio()


def gini(values: Iterable[float]) -> float:
    items = sorted(max(0.0, float(v)) for v in values)
    if not items:
        return 0.0
    total = sum(items)
    if total <= 0:
        return 0.0
    n = len(items)
    weighted = sum((index + 1) * value for index, value in enumerate(items))
    return clamp((2 * weighted) / (n * total) - (n + 1) / n, 0.0, 1.0)


def json_pointer_get(data: Any, pointer: str) -> Any:
    if pointer in ("", "/"):
        return data
    current = data
    for raw_part in pointer.strip("/").split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if 0 <= index < len(current) else None
        else:
            return None
    return current


def json_pointer_set(data: dict[str, Any], pointer: str, value: Any) -> dict[str, Any]:
    if pointer in ("", "/"):
        return value if isinstance(value, dict) else {"value": value}
    current: dict[str, Any] = data
    parts = [part.replace("~1", "/").replace("~0", "~") for part in pointer.strip("/").split("/")]
    for part in parts[:-1]:
        next_value = current.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            current[part] = next_value
        current = next_value
    current[parts[-1]] = value
    return data
