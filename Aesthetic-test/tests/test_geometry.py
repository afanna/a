"""Tests for geometry analyzer."""

import numpy as np
import pytest

from card_scorer.models import BBox, TextElement, ComponentElement
from card_scorer.analyzers.geometry import (
    compute_edge_distances,
    compute_overlaps,
    compute_whitespace_ratio,
    detect_overflow,
    compute_quadrant_density,
)


def _text(x1, y1, x2, y2, text="t"):
    return TextElement(text=text, bbox=BBox(x1, y1, x2, y2), confidence=0.99)


class TestEdgeDistances:
    def test_basic(self):
        elems = [_text(10, 20, 90, 80)]
        result = compute_edge_distances(elems, 100, 100)
        assert len(result) == 1
        assert result[0]["left"] == 10
        assert result[0]["top"] == 20
        assert result[0]["right"] == 10
        assert result[0]["bottom"] == 20
        assert result[0]["min_distance"] == 10


class TestOverlaps:
    def test_no_overlap(self):
        elems = [_text(0, 0, 10, 10), _text(20, 20, 30, 30)]
        assert compute_overlaps(elems) == []

    def test_overlap_detected(self):
        elems = [_text(0, 0, 10, 10), _text(5, 5, 15, 15)]
        result = compute_overlaps(elems, iou_threshold=0.01)
        assert len(result) == 1
        assert result[0]["iou"] > 0


class TestWhitespace:
    def test_empty_card(self):
        ratio = compute_whitespace_ratio([], 100, 100)
        assert ratio == 1.0

    def test_full_card(self):
        elems = [_text(0, 0, 100, 100)]
        ratio = compute_whitespace_ratio(elems, 100, 100)
        assert ratio == pytest.approx(0.0)


class TestOverflow:
    def test_no_overflow(self):
        elems = [_text(10, 10, 90, 90)]
        assert detect_overflow(elems, 100, 100) == []

    def test_overflow_right(self):
        elems = [_text(80, 10, 120, 50)]
        result = detect_overflow(elems, 100, 100)
        assert len(result) == 1
        assert "right" in result[0]["overflow"]


class TestQuadrantDensity:
    def test_single_top_left(self):
        elems = [_text(0, 0, 10, 10)]
        density = compute_quadrant_density(elems, 100, 100)
        assert density["top_left"] > 0
        assert density["bottom_right"] == 0
