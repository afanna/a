"""Tests for Extractors (card_scorer.extractors).

Covers:
- OCR extractor (PaddleOCR + OpenCV fallback)
- Component extractor (connected components)
- Color extractor (KMeans)
- DSL extractor (JSON parse + AST walker)
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytest

from card_scorer.configs.loader import Config
from card_scorer.extractors.color_extractor import extract_colors
from card_scorer.extractors.component_extractor import extract_components
from card_scorer.extractors.dsl_extractor import (
    find_empty_containers,
    get_max_nesting_depth,
    load_dsl,
    walk_dsl,
)
from card_scorer.extractors.ocr_extractor import extract_text
from card_scorer.models import BBox, ColorInfo, ComponentElement, TextElement


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reload_config() -> None:
    Config.reload()


@pytest.fixture
def white_image() -> np.ndarray:
    """200x100 white image."""
    return np.full((100, 200, 3), 255, dtype=np.uint8)


@pytest.fixture
def image_with_rect() -> np.ndarray:
    """200x100 white image with a black rectangle."""
    img = np.full((100, 200, 3), 255, dtype=np.uint8)
    cv2.rectangle(img, (50, 20), (150, 80), (0, 0, 0), -1)
    return img


@pytest.fixture
def image_with_text_like() -> np.ndarray:
    """300x200 white image with text-like dark regions."""
    img = np.full((200, 300, 3), 255, dtype=np.uint8)
    # Simulate text: small dark rectangles
    cv2.rectangle(img, (20, 20), (80, 50), (30, 30, 30), -1)
    cv2.rectangle(img, (20, 60), (120, 90), (30, 30, 30), -1)
    cv2.rectangle(img, (20, 100), (60, 130), (30, 30, 30), -1)
    return img


@pytest.fixture
def color_image() -> np.ndarray:
    """200x100 image with two distinct color regions."""
    img = np.zeros((100, 200, 3), dtype=np.uint8)
    img[0:50, :] = (255, 0, 0)    # Red top half
    img[50:100, :] = (0, 0, 255)  # Blue bottom half
    return img


# ---------------------------------------------------------------------------
# OCR Extractor
# ---------------------------------------------------------------------------

class TestOcrExtractor:
    """Tests for OCR text extraction."""

    def test_extract_text_returns_list(self, white_image: np.ndarray) -> None:
        """extract_text should always return a list."""
        result = extract_text(white_image)
        assert isinstance(result, list)

    def test_extract_text_elements_have_bbox(self, image_with_text_like: np.ndarray) -> None:
        """Each TextElement should have a valid BBox."""
        result = extract_text(image_with_text_like)
        for elem in result:
            assert isinstance(elem, TextElement)
            assert isinstance(elem.bbox, BBox)
            assert elem.bbox.width > 0
            assert elem.bbox.height > 0

    def test_extract_text_elements_have_confidence(self, image_with_text_like: np.ndarray) -> None:
        """Each TextElement should have a confidence value."""
        result = extract_text(image_with_text_like)
        for elem in result:
            assert 0.0 <= elem.confidence <= 1.0

    def test_extract_text_white_image_returns_few(self, white_image: np.ndarray) -> None:
        """White image should return minimal text regions."""
        result = extract_text(white_image)
        # White image has no text, should return 0 or very few
        assert len(result) <= 2

    def test_extract_text_with_custom_cfg(self, image_with_text_like: np.ndarray) -> None:
        """extract_text should accept a custom Config."""
        cfg = Config.load()
        result = extract_text(image_with_text_like, cfg=cfg)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Component Extractor
# ---------------------------------------------------------------------------

class TestComponentExtractor:
    """Tests for connected-component extraction."""

    def test_extract_components_returns_list(self, white_image: np.ndarray) -> None:
        """extract_components should return a list."""
        result = extract_components(white_image)
        assert isinstance(result, list)

    def test_white_image_has_no_components(self, white_image: np.ndarray) -> None:
        """Pure white image should have no components."""
        result = extract_components(white_image)
        assert len(result) == 0

    def test_image_with_rect_has_components(self, image_with_rect: np.ndarray) -> None:
        """Image with a rectangle should detect components."""
        result = extract_components(image_with_rect)
        assert len(result) >= 1

    def test_components_have_valid_bbox(self, image_with_rect: np.ndarray) -> None:
        """Each ComponentElement should have a valid BBox."""
        result = extract_components(image_with_rect)
        for elem in result:
            assert isinstance(elem, ComponentElement)
            assert elem.bbox.width > 0
            assert elem.bbox.height > 0
            assert elem.area > 0

    def test_components_have_centroid(self, image_with_rect: np.ndarray) -> None:
        """Each ComponentElement should have a centroid."""
        result = extract_components(image_with_rect)
        for elem in result:
            assert len(elem.centroid) == 2
            cx, cy = elem.centroid
            assert 0 <= cx
            assert 0 <= cy

    def test_small_components_filtered(self) -> None:
        """Components smaller than min_area should be filtered."""
        img = np.full((100, 200, 3), 255, dtype=np.uint8)
        # Draw a tiny dot (area < 50)
        img[50, 100] = (0, 0, 0)
        result = extract_components(img)
        # The tiny dot should be filtered out
        for elem in result:
            assert elem.area >= 50, f"Component area {elem.area} below min_area"


# ---------------------------------------------------------------------------
# Color Extractor
# ---------------------------------------------------------------------------

class TestColorExtractor:
    """Tests for KMeans color extraction."""

    def test_extract_colors_returns_list(self, color_image: np.ndarray) -> None:
        """extract_colors should return a list of ColorInfo."""
        result = extract_colors(color_image)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_extract_colors_sorted_by_proportion(self, color_image: np.ndarray) -> None:
        """Colors should be sorted by proportion descending."""
        result = extract_colors(color_image)
        for i in range(len(result) - 1):
            assert result[i].proportion >= result[i + 1].proportion

    def test_color_info_has_rgb_and_hsv(self, color_image: np.ndarray) -> None:
        """Each ColorInfo should have RGB and HSV tuples."""
        result = extract_colors(color_image)
        for c in result:
            assert isinstance(c, ColorInfo)
            assert len(c.rgb) == 3
            assert len(c.hsv) == 3
            assert 0.0 <= c.proportion <= 1.0

    def test_extract_colors_with_custom_n(self, color_image: np.ndarray) -> None:
        """Should accept custom n_colors."""
        result = extract_colors(color_image, n_colors=3)
        assert len(result) == 3

    def test_proportions_sum_to_one(self, color_image: np.ndarray) -> None:
        """All color proportions should sum to approximately 1."""
        result = extract_colors(color_image)
        total = sum(c.proportion for c in result)
        assert abs(total - 1.0) < 0.01


# ---------------------------------------------------------------------------
# DSL Extractor
# ---------------------------------------------------------------------------

class TestDslExtractor:
    """Tests for DSL JSON parsing and AST walking."""

    def test_load_dsl_empty_path(self) -> None:
        """Empty path should return None."""
        assert load_dsl("") is None

    def test_load_dsl_nonexistent(self) -> None:
        """Nonexistent file should return None."""
        assert load_dsl("/nonexistent/dsl.json") is None

    def test_load_dsl_valid_json(self) -> None:
        """Valid JSON file should be parsed."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump({"type": "Column", "children": []}, f)
            path = f.name
        try:
            result = load_dsl(path)
            assert result is not None
            assert result["type"] == "Column"
        finally:
            os.unlink(path)

    def test_load_dsl_invalid_json(self) -> None:
        """Invalid JSON should return None."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            f.write("{invalid json")
            path = f.name
        try:
            result = load_dsl(path)
            assert result is None
        finally:
            os.unlink(path)

    def test_walk_dsl_visits_all_nodes(self) -> None:
        """walk_dsl should visit every node."""
        tree = {
            "type": "Column",
            "children": [
                {"type": "Text", "content": "Hello"},
                {"type": "Row", "children": [
                    {"type": "Icon", "name": "weather"},
                ]},
            ],
        }
        visited: list[str] = []

        def visitor(node, depth):
            if isinstance(node, dict) and "type" in node:
                visited.append(node["type"])

        walk_dsl(tree, visitor)
        assert "Column" in visited
        assert "Text" in visited
        assert "Row" in visited
        assert "Icon" in visited

    def test_get_max_nesting_depth_flat(self) -> None:
        """Flat tree should have depth 0."""
        tree = {"type": "Text"}
        assert get_max_nesting_depth(tree) == 0

    def test_get_max_nesting_depth_nested(self) -> None:
        """Nested tree should report correct depth."""
        tree = {
            "type": "A",
            "children": [{
                "type": "B",
                "children": [{
                    "type": "C",
                }],
            }],
        }
        assert get_max_nesting_depth(tree) == 2

    def test_find_empty_containers_finds_empty(self) -> None:
        """Should find containers with empty children."""
        tree = {
            "type": "Column",
            "children": [],
        }
        empty = find_empty_containers(tree)
        assert len(empty) == 1
        assert empty[0]["type"] == "Column"

    def test_find_empty_containers_ignores_nonempty(self) -> None:
        """Should not flag containers with children."""
        tree = {
            "type": "Column",
            "children": [{"type": "Text"}],
        }
        empty = find_empty_containers(tree)
        assert len(empty) == 0
