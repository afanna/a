from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR

from .math_utils import rect_contains, rect_iou
from .models import Rect, TextBlock, VisionContext, VisualElement


_OCR_ENGINE: RapidOCR | None = None


def build_vision_context(image_path: Path) -> VisionContext:
    image = read_image(image_path)
    height, width = image.shape[:2]
    card_bbox = Rect(0, 0, width, height)
    text_blocks = detect_text(image_path, image)
    components = detect_components(image, text_blocks)
    elements = [
        VisualElement(
            kind="text",
            bbox=block.bbox,
            confidence=block.confidence,
            text=block.text,
            layer=3,
            style_features={"font_size": block.font_size, "contrast_ratio": block.contrast_ratio},
        )
        for block in text_blocks
    ]
    elements.extend(components)
    colors, proportions = dominant_colors(image)
    confidence = min([block.confidence for block in text_blocks], default=1.0)
    return VisionContext(
        image_path=image_path,
        width=width,
        height=height,
        card_bbox=card_bbox,
        text_blocks=text_blocks,
        elements=elements,
        dominant_colors=colors,
        color_proportions=proportions,
        confidence=confidence,
    )


def read_image(path: Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Failed to read image: {path}")
    return image


def detect_text(image_path: Path, image: np.ndarray) -> list[TextBlock]:
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        _OCR_ENGINE = RapidOCR()
    result, _ = _OCR_ENGINE(str(image_path))
    blocks: list[TextBlock] = []
    for item in result or []:
        parsed = parse_ocr_item(item)
        if parsed is None:
            continue
        bbox, text, confidence = parsed
        contrast = estimate_text_contrast(image, bbox)
        blocks.append(
            TextBlock(
                text=text,
                bbox=bbox,
                confidence=confidence,
                font_size=max(1.0, bbox.height),
                contrast_ratio=contrast,
            )
        )
    return merge_text_blocks(blocks)


def parse_ocr_item(item: Any) -> tuple[Rect, str, float] | None:
    if not isinstance(item, (list, tuple)) or len(item) < 3:
        return None
    points, text, confidence = item[0], str(item[1] or "").strip(), float(item[2] or 0)
    if not text:
        return None
    pts = np.array(points, dtype=np.float32).reshape(-1, 2)
    x1, y1 = pts.min(axis=0)
    x2, y2 = pts.max(axis=0)
    if x2 <= x1 or y2 <= y1:
        return None
    return Rect(float(x1), float(y1), float(x2 - x1), float(y2 - y1)), text, confidence


def merge_text_blocks(blocks: list[TextBlock]) -> list[TextBlock]:
    if len(blocks) < 2:
        return blocks
    ordered = sorted(blocks, key=lambda item: (item.bbox.y, item.bbox.x))
    merged: list[TextBlock] = []
    for block in ordered:
        if not merged:
            merged.append(block)
            continue
        prev = merged[-1]
        vertical_overlap = _vertical_overlap(prev.bbox, block.bbox)
        gap = block.bbox.x - prev.bbox.x2
        if vertical_overlap > 0.7 and 0 <= gap <= 8:
            bbox = Rect(
                min(prev.bbox.x, block.bbox.x),
                min(prev.bbox.y, block.bbox.y),
                max(prev.bbox.x2, block.bbox.x2) - min(prev.bbox.x, block.bbox.x),
                max(prev.bbox.y2, block.bbox.y2) - min(prev.bbox.y, block.bbox.y),
            )
            merged[-1] = TextBlock(
                text=f"{prev.text} {block.text}",
                bbox=bbox,
                confidence=min(prev.confidence, block.confidence),
                font_size=max(prev.font_size, block.font_size),
                contrast_ratio=min(filter_none([prev.contrast_ratio, block.contrast_ratio]), default=None),
            )
        else:
            merged.append(block)
    return merged


def _vertical_overlap(a: Rect, b: Rect) -> float:
    overlap = max(0.0, min(a.y2, b.y2) - max(a.y, b.y))
    return overlap / max(1.0, min(a.height, b.height))


def filter_none(values: list[float | None]) -> list[float]:
    return [value for value in values if value is not None]


def detect_components(image: np.ndarray, text_blocks: list[TextBlock]) -> list[VisualElement]:
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 150)
    kernel = np.ones((3, 3), dtype=np.uint8)
    edges = cv2.dilate(edges, kernel, iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    elements: list[VisualElement] = []
    total_area = width * height
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        if area < max(25, total_area * 0.001) or area > total_area * 0.65:
            continue
        if w < 4 or h < 4:
            continue
        rect = Rect(float(x), float(y), float(w), float(h))
        if any(rect_iou(rect, block.bbox) > 0.8 for block in text_blocks):
            continue
        contained_texts = text_blocks_inside(rect, text_blocks)
        kind = classify_component(rect, image.shape[1], image.shape[0], contained_texts)
        elements.append(
            VisualElement(
                kind=kind,
                bbox=rect,
                confidence=0.75,
                color=dominant_crop_color(image, rect),
                layer=layer_for_kind(kind),
                radius=estimate_corner_radius(contour, rect),
                style_features=component_style_features(rect, image.shape[1], image.shape[0], contained_texts),
            )
        )
    return merge_elements(elements, text_blocks)


def merge_elements(elements: list[VisualElement], text_blocks: list[TextBlock]) -> list[VisualElement]:
    merged: list[VisualElement] = []
    for element in sorted(elements, key=lambda item: item.bbox.area, reverse=True):
        if any(rect_iou(element.bbox, existing.bbox) > 0.55 for existing in merged):
            continue
        if any(rect_contains(block.bbox, element.bbox, tolerance=2) for block in text_blocks):
            continue
        merged.append(element)
    return list(reversed(merged))


def text_blocks_inside(rect: Rect, text_blocks: list[TextBlock]) -> list[TextBlock]:
    inside: list[TextBlock] = []
    for block in text_blocks:
        cx, cy = block.bbox.center
        if rect.x <= cx <= rect.x2 and rect.y <= cy <= rect.y2:
            inside.append(block)
    return inside


def classify_component(rect: Rect, image_width: int, image_height: int, texts: list[TextBlock]) -> str:
    area_ratio = rect.area / max(1.0, image_width * image_height)
    aspect = rect.width / max(1.0, rect.height)
    max_side = max(rect.width, rect.height)
    min_image_side = min(image_width, image_height)
    if texts:
        return "tag" if area_ratio < 0.08 and rect.height <= image_height * 0.28 else "button"
    if 0.65 <= aspect <= 1.55 and max_side <= min_image_side * 0.36:
        return "icon"
    if area_ratio >= 0.08:
        return "image"
    return "component"


def layer_for_kind(kind: str) -> int:
    return {"image": 1, "component": 1, "icon": 2, "button": 2, "tag": 2, "text": 3}.get(kind, 1)


def dominant_crop_color(image: np.ndarray, rect: Rect) -> tuple[int, int, int] | None:
    height, width = image.shape[:2]
    x1 = max(0, int(rect.x))
    y1 = max(0, int(rect.y))
    x2 = min(width, int(rect.x2))
    y2 = min(height, int(rect.y2))
    if x2 <= x1 or y2 <= y1:
        return None
    rgb = cv2.cvtColor(image[y1:y2, x1:x2], cv2.COLOR_BGR2RGB)
    median = np.median(rgb.reshape(-1, 3), axis=0)
    return tuple(int(round(value)) for value in median)


def estimate_corner_radius(contour: np.ndarray, rect: Rect) -> float | None:
    if rect.width <= 0 or rect.height <= 0:
        return None
    rect_area = rect.width * rect.height
    contour_area = float(cv2.contourArea(contour))
    if contour_area <= 0:
        return None
    fill_ratio = max(0.0, min(1.0, contour_area / rect_area))
    missing_ratio = max(0.0, 1.0 - fill_ratio)
    radius = (missing_ratio ** 0.5) * min(rect.width, rect.height) * 0.65
    return round(float(radius), 2)


def component_style_features(
    rect: Rect,
    image_width: int,
    image_height: int,
    texts: list[TextBlock],
) -> dict[str, float | int | bool | list[float]]:
    features: dict[str, float | int | bool | list[float]] = {
        "area_ratio": round(rect.area / max(1.0, image_width * image_height), 4),
        "aspect_ratio": round(rect.width / max(1.0, rect.height), 4),
        "contains_text": bool(texts),
        "text_count": len(texts),
    }
    if texts:
        min_x = min(block.bbox.x for block in texts)
        min_y = min(block.bbox.y for block in texts)
        max_x = max(block.bbox.x2 for block in texts)
        max_y = max(block.bbox.y2 for block in texts)
        padding = [
            max(0.0, min_x - rect.x),
            max(0.0, rect.x2 - max_x),
            max(0.0, min_y - rect.y),
            max(0.0, rect.y2 - max_y),
        ]
        features["padding"] = [round(float(value), 2) for value in padding]
    return features


def dominant_colors(image: np.ndarray, k: int = 6) -> tuple[list[tuple[int, int, int]], list[float]]:
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    pixels = rgb.reshape(-1, 3).astype(np.float32)
    if len(pixels) > 8000:
        indices = np.linspace(0, len(pixels) - 1, 8000).astype(int)
        pixels = pixels[indices]
    cluster_count = max(1, min(k, len(pixels)))
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 1.0)
    _, labels, centers = cv2.kmeans(pixels, cluster_count, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
    counts = np.bincount(labels.flatten(), minlength=cluster_count)
    order = counts.argsort()[::-1]
    colors: list[tuple[int, int, int]] = []
    proportions: list[float] = []
    total = float(counts.sum() or 1)
    for index in order:
        proportion = counts[index] / total
        if proportion < 0.025:
            continue
        color = tuple(int(round(value)) for value in centers[index])
        colors.append(color)
        proportions.append(float(proportion))
    return colors, proportions


def estimate_text_contrast(image: np.ndarray, bbox: Rect) -> float | None:
    height, width = image.shape[:2]
    x1 = max(0, int(bbox.x))
    y1 = max(0, int(bbox.y))
    x2 = min(width, int(bbox.x2))
    y2 = min(height, int(bbox.y2))
    if x2 <= x1 or y2 <= y1:
        return None
    crop = cv2.cvtColor(image[y1:y2, x1:x2], cv2.COLOR_BGR2RGB)
    if crop.size == 0:
        return None
    border = np.concatenate(
        [
            crop[0:1, :, :].reshape(-1, 3),
            crop[-1:, :, :].reshape(-1, 3),
            crop[:, 0:1, :].reshape(-1, 3),
            crop[:, -1:, :].reshape(-1, 3),
        ],
        axis=0,
    )
    bg = np.median(border, axis=0)
    luma = relative_luminance_array(crop.reshape(-1, 3))
    bg_luma = relative_luminance(bg)
    target = np.percentile(luma, 10 if bg_luma > 0.5 else 90)
    fg_candidates = crop.reshape(-1, 3)
    fg = fg_candidates[np.argmin(np.abs(luma - target))]
    return contrast_ratio(fg, bg)


def relative_luminance_array(rgb: np.ndarray) -> np.ndarray:
    srgb = rgb.astype(np.float32) / 255.0
    linear = np.where(srgb <= 0.03928, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)
    return 0.2126 * linear[:, 0] + 0.7152 * linear[:, 1] + 0.0722 * linear[:, 2]


def relative_luminance(rgb: np.ndarray) -> float:
    return float(relative_luminance_array(np.array([rgb], dtype=np.float32))[0])


def contrast_ratio(foreground: np.ndarray, background: np.ndarray) -> float:
    l1 = relative_luminance(np.asarray(foreground))
    l2 = relative_luminance(np.asarray(background))
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return float((lighter + 0.05) / (darker + 0.05))
