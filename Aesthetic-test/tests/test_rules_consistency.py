"""Tests for visual consistency rules."""

import pytest

from card_scorer.models import BBox, ScoringContext, TextElement, ComponentElement
from card_scorer.rules.consistency import (
    AlignmentConsistencyRule,
    SpacingConsistencyRule,
    FontRhythmRule,
    ComponentRhythmRule,
    IconProportionRule,
    TextImageRatioRule,
    MarginConsistencyRule,
    GridAlignmentRule,
)


def _ctx(features=None, text_elements=None, component_elements=None):
    return ScoringContext(
        text_elements=text_elements or [],
        component_elements=component_elements or [],
        image_width=100,
        image_height=100,
        features=features or {},
    )


def _text(x1, y1, x2, y2, text="t"):
    return TextElement(text=text, bbox=BBox(x1, y1, x2, y2), confidence=0.99)


def _comp(x1, y1, x2, y2, area=None):
    b = BBox(x1, y1, x2, y2)
    return ComponentElement(bbox=b, area=area or b.area, centroid=b.center)


class TestAlignmentConsistencyRule:
    def test_good_alignment(self):
        ctx = _ctx(features={
            "alignment": {"num_left_clusters": 2, "outlier_ratio": 0.1}
        })
        result = AlignmentConsistencyRule().evaluate(ctx)
        assert result.passed is True

    def test_too_many_axes(self):
        ctx = _ctx(features={
            "alignment": {"num_left_clusters": 8, "outlier_ratio": 0.3}
        })
        result = AlignmentConsistencyRule().evaluate(ctx)
        assert result.passed is False

    def test_high_outlier_ratio(self):
        ctx = _ctx(features={
            "alignment": {"num_left_clusters": 3, "outlier_ratio": 0.6}
        })
        result = AlignmentConsistencyRule().evaluate(ctx)
        assert result.passed is False


class TestSpacingConsistencyRule:
    def test_consistent_spacing(self):
        ctx = _ctx(features={
            "spacing": {"cv": 0.1, "mean_gap": 10, "std_gap": 1}
        })
        result = SpacingConsistencyRule().evaluate(ctx)
        assert result.passed is True

    def test_inconsistent_spacing(self):
        ctx = _ctx(features={
            "spacing": {"cv": 0.5, "mean_gap": 10, "std_gap": 5}
        })
        result = SpacingConsistencyRule().evaluate(ctx)
        assert result.passed is False


class TestFontRhythmRule:
    def test_few_levels(self):
        ctx = _ctx(features={
            "font_rhythm": {"size_levels": 2, "sizes": [16, 18]}
        })
        result = FontRhythmRule().evaluate(ctx)
        assert result.passed is True

    def test_too_many_levels(self):
        ctx = _ctx(features={
            "font_rhythm": {"size_levels": 6, "sizes": [10, 12, 14, 16, 18, 20]}
        })
        result = FontRhythmRule().evaluate(ctx)
        assert result.passed is False


class TestComponentRhythmRule:
    def test_few_components(self):
        ctx = _ctx(
            component_elements=[_comp(0, 0, 10, 10)],
            features={"component_rhythm": {"cv": 0.5}}
        )
        result = ComponentRhythmRule().evaluate(ctx)
        assert result.passed is True

    def test_consistent_rhythm(self):
        ctx = _ctx(
            component_elements=[_comp(0, 0, 10, 10), _comp(0, 20, 10, 30), _comp(0, 40, 10, 50)],
            features={"component_rhythm": {"cv": 0.1}}
        )
        result = ComponentRhythmRule().evaluate(ctx)
        assert result.passed is True

    def test_inconsistent_rhythm(self):
        ctx = _ctx(
            component_elements=[_comp(0, 0, 10, 10), _comp(0, 20, 10, 30), _comp(0, 40, 10, 50)],
            features={"component_rhythm": {"cv": 0.5}}
        )
        result = ComponentRhythmRule().evaluate(ctx)
        assert result.passed is False


class TestIconProportionRule:
    def test_no_icons(self):
        ctx = _ctx(features={"icon_proportion": {"ratio": 0.0}})
        result = IconProportionRule().evaluate(ctx)
        assert result.passed is True

    def test_good_proportion(self):
        ctx = _ctx(
            component_elements=[_comp(0, 0, 10, 10)],
            features={"icon_proportion": {"ratio": 0.05}}
        )
        result = IconProportionRule().evaluate(ctx)
        assert result.passed is True

    def test_too_small(self):
        ctx = _ctx(
            component_elements=[_comp(0, 0, 1, 1)],
            features={"icon_proportion": {"ratio": 0.001}}
        )
        result = IconProportionRule().evaluate(ctx)
        assert result.passed is False

    def test_too_large(self):
        ctx = _ctx(
            component_elements=[_comp(0, 0, 50, 50)],
            features={"icon_proportion": {"ratio": 0.3}}
        )
        result = IconProportionRule().evaluate(ctx)
        assert result.passed is False


class TestTextImageRatioRule:
    def test_no_components(self):
        ctx = _ctx(features={"text_image_ratio": 0.5})
        result = TextImageRatioRule().evaluate(ctx)
        assert result.passed is True

    def test_good_ratio(self):
        ctx = _ctx(
            component_elements=[_comp(0, 0, 10, 10)],
            features={"text_image_ratio": 0.5}
        )
        result = TextImageRatioRule().evaluate(ctx)
        assert result.passed is True

    def test_too_much_text(self):
        ctx = _ctx(
            component_elements=[_comp(0, 0, 10, 10)],
            features={"text_image_ratio": 0.95}
        )
        result = TextImageRatioRule().evaluate(ctx)
        assert result.passed is False

    def test_too_much_image(self):
        ctx = _ctx(
            component_elements=[_comp(0, 0, 10, 10)],
            features={"text_image_ratio": 0.1}
        )
        result = TextImageRatioRule().evaluate(ctx)
        assert result.passed is False


class TestMarginConsistencyRule:
    def test_consistent_margins(self):
        ctx = _ctx(features={
            "margin_consistency": {"left_cv": 0.1, "right_cv": 0.1}
        })
        result = MarginConsistencyRule().evaluate(ctx)
        assert result.passed is True

    def test_inconsistent_margins(self):
        ctx = _ctx(features={
            "margin_consistency": {"left_cv": 0.5, "right_cv": 0.2}
        })
        result = MarginConsistencyRule().evaluate(ctx)
        assert result.passed is False


class TestGridAlignmentRule:
    def test_good_snap(self):
        ctx = _ctx(features={
            "grid_alignment": {"x_snap_ratio": 0.8, "y_snap_ratio": 0.7}
        })
        result = GridAlignmentRule().evaluate(ctx)
        assert result.passed is True

    def test_poor_snap(self):
        ctx = _ctx(features={
            "grid_alignment": {"x_snap_ratio": 0.3, "y_snap_ratio": 0.2}
        })
        result = GridAlignmentRule().evaluate(ctx)
        assert result.passed is False
