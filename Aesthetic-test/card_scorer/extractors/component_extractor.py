"""Connected-Component Extractor using OpenCV.

Detects non-text visual elements (icons, images, buttons, decorations)
via ``cv2.connectedComponentsWithStats``.

Output: list[ComponentElement]
"""

from __future__ import annotations

import logging

import cv2
import numpy as np

from card_scorer.configs.loader import Config
from card_scorer.models import BBox, ComponentElement

logger = logging.getLogger(__name__)


def extract_components(
    image: np.ndarray,
    cfg: Config | None = None,
) -> list[ComponentElement]:
    """Detect non-text visual components via connected-component analysis.

    Args:
        image: BGR numpy array.
        cfg: Config instance.

    Returns:
        List of ComponentElement with bbox, area, centroid.
    """
    if cfg is None:
        cfg = Config.load()

    cc_cfg = cfg.threshold_section("connected_components")
    min_area = cc_cfg.get("min_area", 50)
    max_area_ratio = cc_cfg.get("max_area_ratio", 0.5)
    bg_thresh = cc_cfg.get("background_threshold", 240)

    h, w = image.shape[:2]
    image_area = h * w

    # Convert to grayscale and threshold to isolate foreground
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # Invert: foreground becomes white
    _, binary = cv2.threshold(gray, bg_thresh, 255, cv2.THRESH_BINARY_INV)

    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
        binary, connectivity=8
    )

    elements: list[ComponentElement] = []
    for i in range(1, num_labels):  # skip background (label 0)
        area = int(stats[i, cv2.CC_STAT_AREA])

        # Filter by area bounds
        if area < min_area:
            continue
        if area > max_area_ratio * image_area:
            continue

        x = int(stats[i, cv2.CC_STAT_LEFT])
        y = int(stats[i, cv2.CC_STAT_TOP])
        bw = int(stats[i, cv2.CC_STAT_WIDTH])
        bh = int(stats[i, cv2.CC_STAT_HEIGHT])
        cx, cy = float(centroids[i][0]), float(centroids[i][1])

        elements.append(
            ComponentElement(
                bbox=BBox(x1=x, y1=y, x2=x + bw, y2=y + bh),
                area=float(area),
                centroid=(cx, cy),
                label_id=i,
            )
        )

    logger.info("Connected-component analysis found %d elements.", len(elements))
    return elements
