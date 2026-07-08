"""Tests for Context Builder (card_scorer.engine.context).

Covers:
- Image loading and validation
- Keyword extraction from query
- DSL loading
- Full pipeline orchestration
"""

from __future__ import annotations

import json
import os
import tempfile

import cv2
import numpy as np
import pytest

from card_scorer.configs.loader import Config
from card_scorer.engine.context import _extract_keywords, build_context
from card_scorer.models import ScoringContext


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reload_config() -> None:
    Config.reload()


@pytest.fixture
def test_image_path() -> str:
    """Create a temporary test image file."""
    img = np.full((200, 300, 3), 255, dtype=np.uint8)
    cv2.rectangle(img, (20, 20), (100, 50), (30, 30, 30), -1)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        cv2.imwrite(f.name, img)
        return f.name


@pytest.fixture
def test_dsl_path() -> str:
    """Create a temporary DSL JSON file."""
    dsl = {"type": "Column", "children": [{"type": "Text", "content": "Hello"}]}
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(dsl, f)
        return f.name


# ---------------------------------------------------------------------------
# Keyword extraction
# ---------------------------------------------------------------------------

class TestKeywordExtraction:
    """Tests for _extract_keywords()."""

    def test_empty_query(self) -> None:
        """Empty query should return empty list."""
        assert _extract_keywords("") == []
        assert _extract_keywords("   ") == []

    def test_chinese_query(self) -> None:
        """Chinese query should extract keywords."""
        keywords = _extract_keywords("深圳天气怎么样")
        assert len(keywords) >= 2
        assert "深圳" in keywords
        assert "天气" in keywords

    def test_short_words_filtered(self) -> None:
        """Single-character words should be filtered."""
        keywords = _extract_keywords("我是一个测试")
        # "我" and "是" are single chars, should be filtered
        assert all(len(kw) >= 2 for kw in keywords)

    def test_english_query(self) -> None:
        """English query should work."""
        keywords = _extract_keywords("what is the weather")
        assert len(keywords) > 0


# ---------------------------------------------------------------------------
# Context building
# ---------------------------------------------------------------------------

class TestBuildContext:
    """Tests for build_context()."""

    def test_build_context_returns_tuple(self, test_image_path: str) -> None:
        """build_context should return (ScoringContext, np.ndarray)."""
        ctx, img = build_context(test_image_path, query="测试")
        assert isinstance(ctx, ScoringContext)
        assert isinstance(img, np.ndarray)

    def test_build_context_populates_dimensions(self, test_image_path: str) -> None:
        """Context should have image dimensions set."""
        ctx, _ = build_context(test_image_path, query="测试")
        assert ctx.image_width > 0
        assert ctx.image_height > 0

    def test_build_context_populates_query(self, test_image_path: str) -> None:
        """Context should store the query."""
        ctx, _ = build_context(test_image_path, query="深圳天气")
        assert ctx.query == "深圳天气"

    def test_build_context_populates_keywords(self, test_image_path: str) -> None:
        """Context should extract keywords from query."""
        ctx, _ = build_context(test_image_path, query="深圳天气")
        assert len(ctx.keywords) >= 1

    def test_build_context_populates_text_elements(self, test_image_path: str) -> None:
        """Context should have text elements extracted."""
        ctx, _ = build_context(test_image_path, query="测试")
        assert isinstance(ctx.text_elements, list)

    def test_build_context_populates_components(self, test_image_path: str) -> None:
        """Context should have component elements extracted."""
        ctx, _ = build_context(test_image_path, query="测试")
        assert isinstance(ctx.component_elements, list)

    def test_build_context_populates_colors(self, test_image_path: str) -> None:
        """Context should have dominant colors extracted."""
        ctx, _ = build_context(test_image_path, query="测试")
        assert len(ctx.dominant_colors) > 0

    def test_build_context_populates_features(self, test_image_path: str) -> None:
        """Context should have analysis features populated."""
        ctx, _ = build_context(test_image_path, query="测试")
        assert "edge_distances" in ctx.features
        assert "whitespace_ratio" in ctx.features
        assert "alignment" in ctx.features
        assert "spacing" in ctx.features
        assert "visual_center" in ctx.features

    def test_build_context_with_dsl(self, test_image_path: str, test_dsl_path: str) -> None:
        """Context should load DSL when provided."""
        ctx, _ = build_context(
            test_image_path, query="测试", dsl_path=test_dsl_path
        )
        assert ctx.dsl_tree is not None
        assert ctx.dsl_tree["type"] == "Column"

    def test_build_context_without_dsl(self, test_image_path: str) -> None:
        """Context should have None DSL when not provided."""
        ctx, _ = build_context(test_image_path, query="测试")
        assert ctx.dsl_tree is None

    def test_build_context_nonexistent_image(self) -> None:
        """Nonexistent image should raise FileNotFoundError or ValueError."""
        with pytest.raises((FileNotFoundError, ValueError)):
            build_context("/nonexistent/image.png", query="测试")

    def test_build_context_with_custom_config(self, test_image_path: str) -> None:
        """build_context should accept a custom Config."""
        cfg = Config.load()
        ctx, _ = build_context(test_image_path, query="测试", cfg=cfg)
        assert isinstance(ctx, ScoringContext)
