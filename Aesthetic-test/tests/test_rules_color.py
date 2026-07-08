"""Tests for color harmony rules using unified fixtures."""

import pytest
from tests.conftest import assert_rule_failed, assert_rule_passed

from card_scorer.rules.color import (
    TooManyColorsRule,
    ContrastRatioRule,
    HighSaturationRule,
    ColorConflictRule,
)


class TestTooManyColorsRule:
    def test_few_colors(self, make_ctx, make_color):
        ctx = make_ctx(dominant_colors=[
            make_color(255, 0, 0, 0.5),
            make_color(0, 255, 0, 0.3),
            make_color(0, 0, 255, 0.2),
        ])
        result = TooManyColorsRule().evaluate(ctx)
        assert_rule_passed(result, ["dominant_color_count"])

    def test_too_many_colors(self, make_ctx, make_color):
        ctx = make_ctx(dominant_colors=[
            make_color(255, 0, 0, 0.2),
            make_color(0, 255, 0, 0.2),
            make_color(0, 0, 255, 0.2),
            make_color(255, 255, 0, 0.15),
            make_color(255, 0, 255, 0.15),
            make_color(0, 255, 255, 0.1),
        ])
        result = TooManyColorsRule().evaluate(ctx)
        assert_rule_failed(result, expected_evidence_keys=["dominant_color_count"])

    def test_tiny_proportions_ignored(self, make_ctx, make_color):
        ctx = make_ctx(dominant_colors=[
            make_color(255, 0, 0, 0.5),
            make_color(0, 255, 0, 0.3),
            make_color(0, 0, 255, 0.15),
            make_color(255, 255, 0, 0.03),  # Too small, ignored
            make_color(255, 0, 255, 0.01),
            make_color(0, 255, 255, 0.01),
        ])
        result = TooManyColorsRule().evaluate(ctx)
        assert_rule_passed(result)


class TestContrastRatioRule:
    def test_good_contrast(self, make_ctx):
        ctx = make_ctx(features={
            "min_contrast": {"min_ratio": 10.0, "pair": []}
        })
        result = ContrastRatioRule().evaluate(ctx)
        assert_rule_passed(result)

    def test_poor_contrast(self, make_ctx):
        ctx = make_ctx(features={
            "min_contrast": {"min_ratio": 2.0, "pair": [(200, 200, 200), (180, 180, 180)]}
        })
        result = ContrastRatioRule().evaluate(ctx)
        assert_rule_failed(result)


class TestHighSaturationRule:
    def test_no_high_saturation(self, make_ctx):
        ctx = make_ctx(features={"high_saturation": []})
        result = HighSaturationRule().evaluate(ctx)
        assert_rule_passed(result)

    def test_high_saturation_found(self, make_ctx):
        ctx = make_ctx(features={
            "high_saturation": [{"rgb": (255, 0, 0), "saturation": 0.95, "proportion": 0.3}]
        })
        result = HighSaturationRule().evaluate(ctx)
        assert_rule_failed(result)


class TestColorConflictRule:
    def test_no_conflicts(self, make_ctx):
        ctx = make_ctx(features={"color_conflicts": []})
        result = ColorConflictRule().evaluate(ctx)
        assert_rule_passed(result)

    def test_conflict_found(self, make_ctx):
        ctx = make_ctx(features={
            "color_conflicts": [{"color_a": (255, 0, 0), "color_b": (0, 255, 0), "hue_distance": 120}]
        })
        result = ColorConflictRule().evaluate(ctx)
        assert_rule_failed(result)
