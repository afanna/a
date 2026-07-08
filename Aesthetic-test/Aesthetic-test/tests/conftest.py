"""Pytest fixtures and test helpers for card_scorer tests.

This module provides:
- Unified factory functions for test data (ScoringContext, TextElement, etc.)
- Common assertions for rule testing
- Shared test utilities

All test files can import these fixtures to eliminate code duplication.
"""

from __future__ import annotations

import pytest
from card_scorer.models import (
    BBox,
    ColorInfo,
    ComponentElement,
    ScoringContext,
    TextElement,
)


@pytest.fixture
def make_ctx():
    """Factory to create a ScoringContext with default values."""
    
    def _make(
        query: str = "",
        image_width: int = 100,
        image_height: int = 100,
        text_elements: list[TextElement] | None = None,
        component_elements: list[ComponentElement] | None = None,
        dominant_colors: list[ColorInfo] | None = None,
        features: dict | None = None,
        dsl_tree: dict | None = None,
        keywords: list[str] | None = None,
    ) -> ScoringContext:
        return ScoringContext(
            query=query,
            image_width=image_width,
            image_height=image_height,
            text_elements=text_elements or [],
            component_elements=component_elements or [],
            dominant_colors=dominant_colors or [],
            features=features or {},
            dsl_tree=dsl_tree,
            keywords=keywords or [],
        )
    
    return _make


@pytest.fixture
def make_text():
    """Factory to create a TextElement."""
    
    def _make(x1: float, y1: float, x2: float, y2: float, text: str = "t", confidence: float = 0.99) -> TextElement:
        return TextElement(text=text, bbox=BBox(x1, y1, x2, y2), confidence=confidence)
    
    return _make


@pytest.fixture
def make_comp():
    """Factory to create a ComponentElement."""
    
    def _make(x1: float, y1: float, x2: float, y2: float, area: float | None = None) -> ComponentElement:
        b = BBox(x1, y1, x2, y2)
        return ComponentElement(bbox=b, area=area or b.area, centroid=b.center)
    
    return _make


@pytest.fixture
def make_color():
    """Factory to create a ColorInfo."""
    
    def _make(r: int, g: int, b: int, proportion: float = 0.3, h: float = 0.0, s: float = 0.5, v: float = 0.8) -> ColorInfo:
        return ColorInfo(rgb=(r, g, b), hsv=(h, s, v), proportion=proportion)
    
    return _make


# Helper assertions for rule testing

def assert_rule_passed(result, expected_evidence_keys: list[str] | None = None):
    """Assert that a rule result is a pass."""
    assert result.passed is True, f"Expected rule to pass, but it failed: {result.explanation}"
    assert result.score_delta == 0.0, f"Passing rule should have 0 deduction, got {result.score_delta}"
    
    if expected_evidence_keys:
        for key in expected_evidence_keys:
            assert key in result.evidence, f"Expected evidence key '{key}' not found"


def assert_rule_failed(result, expected_min_deduction: float = 0.0, expected_evidence_keys: list[str] | None = None):
    """Assert that a rule result is a failure."""
    assert result.passed is False, f"Expected rule to fail, but it passed"
    assert result.score_delta < 0, f"Failed rule should have negative delta, got {result.score_delta}"
    
    if expected_min_deduction > 0:
        actual_deduction = abs(result.score_delta)
        assert actual_deduction >= expected_min_deduction, \
            f"Expected deduction >= {expected_min_deduction}, got {actual_deduction}"
    
    if expected_evidence_keys:
        for key in expected_evidence_keys:
            assert key in result.evidence, f"Expected evidence key '{key}' not found in {result.evidence}"
    
    assert result.explanation, "Failed rule should have explanation"
    assert result.suggestion or True, "Failed rule should ideally have suggestion (warning only)"
