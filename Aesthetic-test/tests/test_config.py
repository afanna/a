"""Tests for configuration loader."""

import pytest

from card_scorer.configs.loader import Config


class TestConfig:
    def setup_method(self):
        """Force reload config for each test."""
        self.cfg = Config.reload()

    def test_base_score(self):
        assert self.cfg.base_score == 100

    def test_fail_cap(self):
        assert self.cfg.fail_cap == 60

    def test_weight_access(self):
        max_ded = self.cfg.weight("information", "max_deduction")
        assert max_ded == 25

    def test_threshold_access(self):
        margin = self.cfg.threshold("layout", "edge_margin_min_px")
        assert margin == 16

    def test_threshold_section(self):
        section = self.cfg.threshold_section("ocr")
        assert "lang" in section
        assert section["lang"] == "ch"

    def test_missing_weight_raises(self):
        with pytest.raises(KeyError):
            self.cfg.weight("information", "nonexistent_key")

    def test_missing_threshold_raises(self):
        with pytest.raises(KeyError):
            self.cfg.threshold("layout", "nonexistent_key")
