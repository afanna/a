"""Tests for visual hierarchy rules."""

import pytest

from card_scorer.models import BBox, ScoringContext, TextElement
from card_scorer.rules.hierarchy import (
    VisualCenterOffsetRule,
    DensityBalanceRule,
    SizeHierarchyRule,
)


def _ctx(features=None, text_elements=None):
    return ScoringContext(
        text_elements=text_elements or [],
        features=features or {},
    )


def _text(x1, y1, x2, y2, text="t"):
    return TextElement(text=text, bbox=BBox(x1, y1, x2, y2), confidence=0.99)


class TestVisualCenterOffsetRule:
    def test_centered(self):
        ctx = _ctx(features={
            "visual_center_offset": {"offset_norm": 0.05, "offset_x": 0.02, "offset_y": 0.03}
        })
        result = VisualCenterOffsetRule().evaluate(ctx)
        assert result.passed is True

    def test_offset(self):
        ctx = _ctx(features={
            "visual_center_offset": {"offset_norm": 0.3, "offset_x": 0.2, "offset_y": 0.2}
        })
        result = VisualCenterOffsetRule().evaluate(ctx)
        assert result.passed is False


class TestDensityBalanceRule:
    def test_balanced(self):
        ctx = _ctx(features={
            "density_balance": {"ratio": 1.5, "max_quadrant": "top_left", "min_quadrant": "bottom_right"}
        })
        result = DensityBalanceRule().evaluate(ctx)
        assert result.passed is True

    def test_unbalanced(self):
        ctx = _ctx(features={
            "density_balance": {"ratio": 5.0, "max_quadrant": "top_left", "min_quadrant": "bottom_right"}
        })
        result = DensityBalanceRule().evaluate(ctx)
        assert result.passed is False


class TestSizeHierarchyRule:
    def test_good_ratio(self):
        ctx = _ctx(
            text_elements=[
                _text(0, 0, 100, 30),
                _text(0, 40, 100, 56),
            ],
            features={
                "size_hierarchy": {"max_size": 30, "median_size": 16, "ratio": 1.875}
            }
        )
        result = SizeHierarchyRule().evaluate(ctx)
        assert result.passed is True

    def test_too_small_ratio(self):
        ctx = _ctx(
            text_elements=[
                _text(0, 0, 100, 16),
                _text(0, 20, 100, 36),
            ],
            features={
                "size_hierarchy": {"max_size": 16, "median_size": 16, "ratio": 1.0}
            }
        )
        result = SizeHierarchyRule().evaluate(ctx)
        assert result.passed is False

    def test_too_few_elements(self):
        ctx = _ctx(
            text_elements=[_text(0, 0, 100, 20)],
            features={"size_hierarchy": {"max_size": 20, "median_size": 20, "ratio": 1.0}}
        )
        result = SizeHierarchyRule().evaluate(ctx)
        assert result.passed is True
