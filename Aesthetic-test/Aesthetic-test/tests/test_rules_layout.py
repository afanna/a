"""Tests for layout & whitespace rules."""

import pytest

from card_scorer.models import BBox, ScoringContext, TextElement
from card_scorer.rules.layout import (
    EdgeProximityRule,
    ElementOverlapRule,
    WhitespaceRatioRule,
    ElementOverflowRule,
)


def _ctx(features=None, text_elements=None):
    return ScoringContext(
        text_elements=text_elements or [],
        image_width=100,
        image_height=100,
        features=features or {},
    )


def _text(x1, y1, x2, y2, text="t"):
    return TextElement(text=text, bbox=BBox(x1, y1, x2, y2), confidence=0.99)


class TestEdgeProximityRule:
    def test_safe_distance(self):
        ctx = _ctx(features={
            "edge_distances": [
                {"element_index": 0, "min_distance": 30, "left": 30, "top": 30, "right": 30, "bottom": 30}
            ]
        })
        result = EdgeProximityRule().evaluate(ctx)
        assert result.passed is True

    def test_too_close(self):
        ctx = _ctx(features={
            "edge_distances": [
                {"element_index": 0, "min_distance": 4, "left": 4, "top": 20, "right": 50, "bottom": 20}
            ]
        })
        result = EdgeProximityRule().evaluate(ctx)
        assert result.passed is False
        assert result.score_delta < 0

    def test_no_elements(self):
        ctx = _ctx(features={"edge_distances": []})
        result = EdgeProximityRule().evaluate(ctx)
        assert result.passed is True


class TestElementOverlapRule:
    def test_no_overlap(self):
        ctx = _ctx(features={"overlaps": []})
        result = ElementOverlapRule().evaluate(ctx)
        assert result.passed is True

    def test_overlap_found(self):
        ctx = _ctx(features={"overlaps": [{"idx_a": 0, "idx_b": 1, "iou": 0.3}]})
        result = ElementOverlapRule().evaluate(ctx)
        assert result.passed is False
        assert result.score_delta < 0


class TestWhitespaceRatioRule:
    def test_good_ratio(self):
        ctx = _ctx(features={"whitespace_ratio": 0.4})
        result = WhitespaceRatioRule().evaluate(ctx)
        assert result.passed is True

    def test_too_low(self):
        ctx = _ctx(features={"whitespace_ratio": 0.05})
        result = WhitespaceRatioRule().evaluate(ctx)
        assert result.passed is False

    def test_too_high(self):
        ctx = _ctx(features={"whitespace_ratio": 0.95})
        result = WhitespaceRatioRule().evaluate(ctx)
        assert result.passed is False


class TestElementOverflowRule:
    def test_no_overflow(self):
        ctx = _ctx(features={"overflows": []})
        result = ElementOverflowRule().evaluate(ctx)
        assert result.passed is True

    def test_overflow_found(self):
        ctx = _ctx(features={"overflows": [{"element_index": 0, "overflow": {"right": 10}}]})
        result = ElementOverflowRule().evaluate(ctx)
        assert result.passed is False
        assert result.score_delta < 0
