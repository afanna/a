"""Pipeline Context Builder.

Orchestrates the extraction and analysis pipeline to build a
fully populated ScoringContext.

Flow:
    Image -> OCR + ConnectedComponents + Color extraction
    Query -> jieba keyword extraction
    DSL   -> json parse (optional)
    -> Geometry analysis
    -> Consistency analysis
    -> Hierarchy analysis
    -> Aesthetics analysis
"""

from __future__ import annotations

import logging

import cv2
import jieba
import numpy as np

from card_scorer.analyzers import geometry, consistency, hierarchy, aesthetics
from card_scorer.configs.loader import Config
from card_scorer.extractors.color_extractor import extract_colors
from card_scorer.extractors.component_extractor import extract_components
from card_scorer.extractors.dsl_extractor import load_dsl
from card_scorer.extractors.ocr_extractor import extract_text
from card_scorer.models import ScoringContext

logger = logging.getLogger(__name__)


def _extract_keywords(query: str) -> list[str]:
    """Extract keywords from query using jieba."""
    if not query.strip():
        return []
    # Filter out short/stop words
    words = jieba.lcut(query)
    return [w for w in words if len(w) >= 2]


def build_context(
    image_path: str,
    query: str = "",
    dsl_path: str = "",
    cfg: Config | None = None,
) -> tuple[ScoringContext, np.ndarray]:
    """Build a fully populated ScoringContext.

    Args:
        image_path: Path to the card screenshot.
        query: User query that generated this card.
        dsl_path: Optional path to DSL JSON file.
        cfg: Config instance.

    Returns:
        Tuple of (ScoringContext, image_array).

    Raises:
        FileNotFoundError: If image_path doesn't exist.
        ValueError: If image cannot be loaded.
    """
    if cfg is None:
        cfg = Config.load()

    # Load image
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Cannot load image: {image_path}")

    h, w = image.shape[:2]
    logger.info("Loaded image %s (%dx%d)", image_path, w, h)

    # Build context
    ctx = ScoringContext(
        query=query,
        image_path=image_path,
        dsl_path=dsl_path,
        image_width=w,
        image_height=h,
    )

    # --- Extraction ---
    ctx.text_elements = extract_text(image, cfg)
    ctx.component_elements = extract_components(image, cfg)
    ctx.dominant_colors = extract_colors(image, cfg)
    ctx.keywords = _extract_keywords(query)

    # ✨ P0-2 修复：记录 DSL 解析状态
    dsl_tree, dsl_status = load_dsl(dsl_path)
    ctx.dsl_tree = dsl_tree
    ctx.dsl_status = dsl_status  # "OK" | "NOT_PROVIDED" | "FILE_NOT_FOUND" | "PARSE_FAILED"

    if dsl_status != "OK" and dsl_path:
        logger.warning("DSL load status: %s (path: %s)", dsl_status, dsl_path)

    # --- Analysis ---
    geometry.analyze(ctx, image)
    consistency.analyze(ctx)
    hierarchy.analyze(ctx)
    aesthetics.analyze(ctx)

    logger.info("Context built: %d text, %d components, %d colors, %d keywords",
                len(ctx.text_elements), len(ctx.component_elements),
                len(ctx.dominant_colors), len(ctx.keywords))
    return ctx, image
