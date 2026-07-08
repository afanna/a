"""OCR Extractor using RapidOCR with OpenCV fallback.

Extracts text regions from a card screenshot.
Uses RapidOCR (ONNX Runtime) as the primary engine -- lightweight,
no PaddlePaddle dependency, works on Windows/Linux/Mac out of the box.
Falls back to OpenCV contour-based detection if RapidOCR is unavailable.

Output: list[TextElement]
"""

from __future__ import annotations

import logging
from typing import Any

import cv2
import numpy as np

from card_scorer.configs.loader import Config
from card_scorer.models import BBox, TextElement

logger = logging.getLogger(__name__)

# Lazy-loaded RapidOCR instance
_ocr_engine: Any = None
_ocr_failed: bool = False


def _get_ocr_engine() -> Any | None:
    """Lazy-init RapidOCR engine. Returns None if unavailable."""
    global _ocr_engine, _ocr_failed
    if _ocr_engine is not None:
        return _ocr_engine
    if _ocr_failed:
        return None

    try:
        from rapidocr_onnxruntime import RapidOCR
        _ocr_engine = RapidOCR()
        logger.info("RapidOCR engine initialized.")
        return _ocr_engine
    except Exception as e:
        logger.warning("RapidOCR init failed: %s. Using OpenCV fallback.", e)
        _ocr_failed = True
        return None


def _polygon_to_bbox(polygon: list[list[float]]) -> BBox:
    """Convert OCR polygon (4 points) to axis-aligned BBox."""
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return BBox(x1=min(xs), y1=min(ys), x2=max(xs), y2=max(ys))


def _extract_text_fallback(image: np.ndarray) -> list[TextElement]:
    """OpenCV-based text region detection fallback.

    Uses adaptive thresholding + contour detection to find text-like regions.
    Does not provide actual text content, only bounding boxes.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 11, 2,
    )
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    morphed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(
        morphed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE,
    )

    h, w = image.shape[:2]
    img_area = h * w
    elements: list[TextElement] = []

    for c in contours:
        x, y, bw, bh = cv2.boundingRect(c)
        area = bw * bh
        if area < 30 or area > img_area * 0.8 or bw < 5 or bh < 5:
            continue
        bbox = BBox(x1=float(x), y1=float(y), x2=float(x + bw), y2=float(y + bh))
        elements.append(TextElement(
            text="",
            bbox=bbox,
            confidence=0.5,
            font_size_est=float(bh),
        ))

    logger.info("Fallback OCR found %d text-like regions.", len(elements))
    return elements


def extract_text(
    image: np.ndarray,
    cfg: Config | None = None,
) -> list[TextElement]:
    """Run OCR on an image and return TextElement list.

    Args:
        image: BGR numpy array (as loaded by cv2.imread).
        cfg: Config instance; loaded automatically if None.

    Returns:
        List of TextElement with text, bbox, confidence, and estimated font size.
    """
    if cfg is None:
        cfg = Config.load()

    ocr = _get_ocr_engine()
    if ocr is None:
        return _extract_text_fallback(image)

    ocr_cfg = cfg.threshold_section("ocr")
    score_threshold = ocr_cfg.get("rec_score_threshold", 0.5)

    result, _ = ocr(image)
    if not result:
        logger.warning("OCR returned no results.")
        return []

    elements: list[TextElement] = []
    for line in result:
        polygon, text, confidence = line
        if confidence < score_threshold:
            continue
        bbox = _polygon_to_bbox(polygon)
        elements.append(
            TextElement(
                text=text,
                bbox=bbox,
                confidence=confidence,
                font_size_est=bbox.height,
            )
        )

    logger.info("OCR extracted %d text elements.", len(elements))
    return elements
