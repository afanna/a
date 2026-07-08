"""Tests for aesthetics analyzer."""

import pytest

from card_scorer.analyzers.aesthetics import contrast_ratio, _relative_luminance


class TestContrastRatio:
    def test_black_white(self):
        # WCAG: max contrast is 21:1
        cr = contrast_ratio((0, 0, 0), (255, 255, 255))
        assert cr == pytest.approx(21.0, rel=0.01)

    def test_same_color(self):
        cr = contrast_ratio((128, 128, 128), (128, 128, 128))
        assert cr == pytest.approx(1.0)

    def test_symmetry(self):
        cr1 = contrast_ratio((255, 0, 0), (0, 0, 255))
        cr2 = contrast_ratio((0, 0, 255), (255, 0, 0))
        assert cr1 == pytest.approx(cr2)
