"""Tests for core data models."""

import pytest

from card_scorer.models import BBox, Severity, RuleResult, DimensionScore


class TestBBox:
    def test_width_height(self):
        b = BBox(10, 20, 110, 70)
        assert b.width == 100
        assert b.height == 50

    def test_area(self):
        b = BBox(0, 0, 10, 10)
        assert b.area == 100

    def test_area_zero(self):
        b = BBox(5, 5, 5, 5)
        assert b.area == 0

    def test_center(self):
        b = BBox(0, 0, 100, 200)
        assert b.center == (50, 100)

    def test_iou_no_overlap(self):
        a = BBox(0, 0, 10, 10)
        b = BBox(20, 20, 30, 30)
        assert a.iou(b) == 0.0

    def test_iou_full_overlap(self):
        a = BBox(0, 0, 10, 10)
        assert a.iou(a) == pytest.approx(1.0)

    def test_iou_partial(self):
        a = BBox(0, 0, 10, 10)
        b = BBox(5, 5, 15, 15)
        # Intersection: 5x5 = 25, Union: 100 + 100 - 25 = 175
        assert a.iou(b) == pytest.approx(25 / 175)


class TestRuleResult:
    def test_creation(self):
        r = RuleResult(
            rule_id="R1.1",
            rule_name="test",
            dimension="information",
            passed=False,
            score_delta=-5.0,
            severity=Severity.MAJOR,
            evidence={"key": "value"},
            explanation="test explanation",
            suggestion="fix it",
        )
        assert r.rule_id == "R1.1"
        assert r.passed is False
        assert r.score_delta == -5.0


class TestDimensionScore:
    def test_score_calculation(self):
        ds = DimensionScore(
            dimension="layout",
            dimension_name="布局",
            max_deduction=20,
            actual_deduction=8,
        )
        assert ds.score == 12.0

    def test_score_clamped_to_zero(self):
        ds = DimensionScore(
            dimension="layout",
            dimension_name="布局",
            max_deduction=20,
            actual_deduction=25,
        )
        assert ds.score == 0.0
