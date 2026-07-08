"""Color Extractor using KMeans clustering.

Extracts dominant colors from a card screenshot.
Output: list[ColorInfo]
"""

from __future__ import annotations

import colorsys
import logging

import cv2
import numpy as np
from sklearn.cluster import KMeans

from card_scorer.configs.loader import Config
from card_scorer.models import ColorInfo

logger = logging.getLogger(__name__)


def extract_colors(
    image: np.ndarray,
    cfg: Config | None = None,
    n_colors: int | None = None,
) -> list[ColorInfo]:
    """Extract dominant colors from an image via KMeans.

    Args:
        image: BGR numpy array.
        cfg: Config instance.
        n_colors: Number of clusters. Defaults to ``color.max_dominant_colors``.

    Returns:
        List of ColorInfo sorted by proportion (descending).
    """
    if cfg is None:
        cfg = Config.load()

    if n_colors is None:
        n_colors = cfg.threshold("color", "max_dominant_colors")

    # Downsample for speed
    h, w = image.shape[:2]
    max_pixels = 10000
    if h * w > max_pixels:
        scale = (max_pixels / (h * w)) ** 0.5
        image = cv2.resize(image, (int(w * scale), int(h * scale)))

    # Reshape to (N, 3) RGB
    rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    pixels = rgb_image.reshape(-1, 3).astype(np.float64)

    kmeans = KMeans(n_clusters=n_colors, n_init=3, random_state=42)
    kmeans.fit(pixels)

    # Count pixels per cluster
    labels = kmeans.labels_
    counts = np.bincount(labels, minlength=n_colors)
    total = len(labels)

    colors: list[ColorInfo] = []
    for i in range(n_colors):
        r, g, b = [int(v) for v in kmeans.cluster_centers_[i]]
        h_val, s_val, v_val = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        proportion = counts[i] / total if total > 0 else 0.0
        colors.append(
            ColorInfo(
                rgb=(r, g, b),
                hsv=(h_val, s_val, v_val),
                proportion=proportion,
            )
        )

    # Sort by proportion descending
    colors.sort(key=lambda c: c.proportion, reverse=True)
    logger.info("Extracted %d dominant colors.", len(colors))
    return colors
