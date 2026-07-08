"""Tests for consistency analyzer."""

import pytest

from card_scorer.models import BBox, TextElement
from card_scorer.analyzers.consistency import (
    compute_alignment_clusters,
    compute_spacing_variance,
    compute_font_rhythm,
)


def _text(x1, y1, x2, y2, text="t"):
    return TextElement(text=text, bbox=BBox(x1, y1, x2, y2), confidence=0.99)


class TestAlignmentClusters:
    def test_perfectly_aligned(self):
        elems = [_text(20, 10, 80, 30), _text(20, 40, 80, 60), _text(20, 70, 80, 90)]
        result = compute_alignment_clusters(elems, eps=5)
        assert result["num_left_clusters"] == 1
        assert result["outlier_ratio"] == 0.0

    def test_multiple_axes(self):
        elems = [_text(20, 10, 80, 30), _text(50, 40, 90, 60), _text(80, 70, 120, 90)]
        result = compute_alignment_clusters(elems, eps=5)
        assert result["num_left_clusters"] == 3


class TestSpacingVariance:
    def test_uniform_spacing(self):
        elems = [_text(0, 0, 10, 10), _text(0, 20, 10, 30), _text(0, 40, 10, 50)]
        result = compute_spacing_variance(elems)
        assert result["cv"] == pytest.approx(0.0)

    def test_varied_spacing(self):
        elems = [_text(0, 0, 10, 10), _text(0, 15, 10, 25), _text(0, 60, 10, 70)]
        result = compute_spacing_variance(elems)
        assert result["cv"] > 0


class TestFontRhythm:
    def test_single_size(self):
        elems = [_text(0, 0, 100, 20), _text(0, 30, 100, 50)]
        result = compute_font_rhythm(elems)
        assert result["size_levels"] == 1

    def test_multiple_sizes(self):
        elems = [_text(0, 0, 100, 30), _text(0, 40, 100, 56)]
        result = compute_font_rhythm(elems)
        assert result["size_levels"] == 2
