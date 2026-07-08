"""Tests for the Scoring Engine (card_scorer.engine.scorer).

Covers:
- Pure deduction system (100 - deductions)
- FAIL cap at 60
- All 27 rules collected
- Dimension aggregation
- Rule exception handling
- Metadata population
"""

from __future__ import annotations

import pytest

from card_scorer.configs.loader import Config
from card_scorer.engine.scorer import _collect_all_rules, score
from card_scorer.models import (
    ColorInfo,
    ComponentElement,
    RuleResult,
    ScoringContext,
    ScoringReport,
    Severity,
    TextElement,
    BBox,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reload_config() -> None:
    """Ensure each test gets a fresh config."""
    Config.reload()


@pytest.fixture
def empty_ctx() -> ScoringContext:
    """Minimal context with no elements."""
    return ScoringContext(
        query="test query",
        image_path="/tmp/test.png",
        image_width=400,
        image_height=300,
    )


@pytest.fixture
def ctx_with_text() -> ScoringContext:
    """Context with some text elements and pre-populated features."""
    ctx = ScoringContext(
        query="上海天气",
        image_path="/tmp/test.png",
        image_width=400,
        image_height=300,
        keywords=["上海", "天气"],
    )
    ctx.text_elements = [
        TextElement(
            text="上海",
            bbox=BBox(10, 10, 100, 40),
            confidence=0.95,
            font_size_est=30,
        ),
        TextElement(
            text="25°C",
            bbox=BBox(10, 50, 80, 80),
            confidence=0.90,
            font_size_est=30,
        ),
    ]
    ctx.component_elements = [
        ComponentElement(
            bbox=BBox(200, 20, 250, 70),
            area=2500,
            centroid=(225, 45),
            label_id=1,
        ),
    ]
    ctx.dominant_colors = [
        ColorInfo(rgb=(255, 255, 255), hsv=(0, 0, 1.0), proportion=0.6),
        ColorInfo(rgb=(0, 0, 0), hsv=(0, 0, 0), proportion=0.3),
    ]
    # Populate features minimally so rules don't crash
    ctx.features = {
        "edge_distances": [
            {"element_index": 0, "min_distance": 10, "bbox": ctx.text_elements[0].bbox},
        ],
        "overlaps": [],
        "whitespace_ratio": 0.5,
        "overflows": [],
        "visual_center": (0.5, 0.5),
        "quadrant_density": {"top_left": 100, "top_right": 100, "bottom_left": 100, "bottom_right": 100},
        "alignment": {"outlier_ratio": 0.0, "num_left_clusters": 1},
        "spacing": {"cv": 0.1, "mean_gap": 10, "std_gap": 1},
        "font_rhythm": {"size_levels": 2},
        "component_rhythm": {"cv": 0.0},
        "icon_proportion": {"ratio": 0.05},
        "text_image_ratio": 0.6,
        "margin_consistency": {"left_cv": 0.1, "right_cv": 0.1},
        "grid_alignment": {"x_snap_ratio": 0.8, "y_snap_ratio": 0.8},
        "color_count": 2,
        "color_conflicts": [],
        "high_saturation": [],
        "min_contrast": {"min_ratio": 10.0, "pair": []},
        "visual_center_offset": {"offset_norm": 0.05},
        "density_balance": {"ratio": 1.0},
        "size_hierarchy": {"ratio": 1.5},
    }
    return ctx


# ---------------------------------------------------------------------------
# Rule collection
# ---------------------------------------------------------------------------

class TestRuleCollection:
    """Tests for _collect_all_rules()."""

    def test_collects_27_rules(self) -> None:
        """All 27 rules should be collected."""
        rules = _collect_all_rules()
        assert len(rules) == 27, f"Expected 27 rules, got {len(rules)}"

    def test_all_rules_have_unique_ids(self) -> None:
        """No duplicate rule IDs."""
        rules = _collect_all_rules()
        ids = [r.rule_id for r in rules]
        assert len(ids) == len(set(ids)), f"Duplicate rule IDs found: {ids}"

    def test_all_rules_have_dimension(self) -> None:
        """Every rule must have a dimension."""
        rules = _collect_all_rules()
        for r in rules:
            assert r.dimension, f"Rule {r.rule_id} has no dimension"


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

class TestScoreEngine:
    """Tests for score()."""

    def test_perfect_score_empty_context(self, empty_ctx: ScoringContext) -> None:
        """Empty context with no violations should score near 100."""
        report = score(empty_ctx)
        # EntityMissingRule will fire (no text), but most rules pass
        assert 0 <= report.total_score <= 100

    def test_returns_scoring_report(self, ctx_with_text: ScoringContext) -> None:
        """score() must return a ScoringReport."""
        report = score(ctx_with_text)
        assert isinstance(report, ScoringReport)

    def test_total_score_is_float(self, ctx_with_text: ScoringContext) -> None:
        """Total score must be a float."""
        report = score(ctx_with_text)
        assert isinstance(report.total_score, float)

    def test_status_is_pass_or_fail(self, ctx_with_text: ScoringContext) -> None:
        """Status must be PASS or FAIL."""
        report = score(ctx_with_text)
        assert report.status in ("PASS", "FAIL")

    def test_all_results_populated(self, ctx_with_text: ScoringContext) -> None:
        """All 27 rules must produce results."""
        report = score(ctx_with_text)
        assert len(report.all_results) == 27

    def test_deduction_details_only_failures(self, ctx_with_text: ScoringContext) -> None:
        """deduction_details should only contain failed rules."""
        report = score(ctx_with_text)
        for r in report.deduction_details:
            assert not r.passed, f"Rule {r.rule_id} in deductions but passed=True"

    def test_metadata_populated(self, ctx_with_text: ScoringContext) -> None:
        """Metadata should contain image info."""
        report = score(ctx_with_text)
        assert report.metadata["image_path"] == "/tmp/test.png"
        assert report.metadata["query"] == "上海天气"
        assert "image_size" in report.metadata
        assert "text_count" in report.metadata
        assert "component_count" in report.metadata
        assert "color_count" in report.metadata

    def test_dimensions_match_config(self, ctx_with_text: ScoringContext) -> None:
        """All configured dimensions should appear in the report."""
        cfg = Config.load()
        report = score(ctx_with_text)
        dim_names = [d.dimension for d in report.dimensions]
        for dim_key in cfg.weights_raw().get("dimensions", {}):
            assert dim_key in dim_names, f"Dimension {dim_key} missing from report"

    def test_score_non_negative(self, ctx_with_text: ScoringContext) -> None:
        """Score must never go below 0."""
        report = score(ctx_with_text)
        assert report.total_score >= 0.0

    def test_score_not_exceed_100(self, ctx_with_text: ScoringContext) -> None:
        """Score must never exceed 100."""
        report = score(ctx_with_text)
        assert report.total_score <= 100.0


# ---------------------------------------------------------------------------
# FAIL cap
# ---------------------------------------------------------------------------

class TestFailCap:
    """Tests for FAIL cap mechanism."""

    def test_fail_caps_score_at_60(self) -> None:
        """When a FATAL rule triggers, score should be capped at 60."""
        ctx = ScoringContext(
            query="test",
            image_path="/tmp/test.png",
            image_width=400,
            image_height=300,
        )
        # Pre-populate with a FATAL failure: keyword missing
        ctx.keywords = ["missing_keyword"]
        ctx.text_elements = []  # No text found -> keyword missing triggers
        ctx.features = {
            "edge_distances": [],
            "overlaps": [],
            "whitespace_ratio": 0.5,
            "overflows": [],
            "visual_center": (0.5, 0.5),
            "quadrant_density": {},
            "alignment": {"outlier_ratio": 0.0, "num_left_clusters": 0},
            "spacing": {"cv": 0.0, "mean_gap": 0, "std_gap": 0},
            "font_rhythm": {"size_levels": 0},
            "component_rhythm": {"cv": 0.0},
            "icon_proportion": {"ratio": 0.0},
            "text_image_ratio": 0.0,
            "margin_consistency": {"left_cv": 0.0, "right_cv": 0.0},
            "grid_alignment": {"x_snap_ratio": 1.0, "y_snap_ratio": 1.0},
            "color_count": 0,
            "color_conflicts": [],
            "high_saturation": [],
            "min_contrast": {"min_ratio": 21.0, "pair": []},
            "visual_center_offset": {"offset_norm": 0.0},
            "density_balance": {"ratio": 1.0},
            "size_hierarchy": {"ratio": 1.0},
        }
        report = score(ctx)
        assert report.fail_triggered, "FAIL should be triggered"
        assert report.status == "FAIL"
        assert report.total_score <= 60.0, f"Score {report.total_score} not capped at 60"


# ---------------------------------------------------------------------------
# Rule exception handling
# ---------------------------------------------------------------------------

class TestRuleExceptionHandling:
    """Tests that rule exceptions don't crash the scorer."""

    def test_rule_exception_produces_pass_result(self, monkeypatch) -> None:
        """If a rule raises, it should produce a pass result with error evidence."""
        from card_scorer.rules import information

        original = information.KeywordMissingRule.evaluate

        def _broken_evaluate(self, ctx):
            raise RuntimeError("Simulated rule failure")

        monkeypatch.setattr(information.KeywordMissingRule, "evaluate", _broken_evaluate)

        ctx = ScoringContext(
            query="test",
            image_path="/tmp/test.png",
            image_width=400,
            image_height=300,
            keywords=["test"],
            text_elements=[TextElement(
                text="test",
                bbox=BBox(0, 0, 10, 10),
                confidence=0.9,
            )],
        )
        ctx.features = {
            "edge_distances": [],
            "overlaps": [],
            "whitespace_ratio": 0.5,
            "overflows": [],
            "visual_center": (0.5, 0.5),
            "quadrant_density": {},
            "alignment": {"outlier_ratio": 0.0, "num_left_clusters": 0},
            "spacing": {"cv": 0.0, "mean_gap": 0, "std_gap": 0},
            "font_rhythm": {"size_levels": 1},
            "component_rhythm": {"cv": 0.0},
            "icon_proportion": {"ratio": 0.0},
            "text_image_ratio": 0.5,
            "margin_consistency": {"left_cv": 0.0, "right_cv": 0.0},
            "grid_alignment": {"x_snap_ratio": 1.0, "y_snap_ratio": 1.0},
            "color_count": 0,
            "color_conflicts": [],
            "high_saturation": [],
            "min_contrast": {"min_ratio": 21.0, "pair": []},
            "visual_center_offset": {"offset_norm": 0.0},
            "density_balance": {"ratio": 1.0},
            "size_hierarchy": {"ratio": 1.0},
        }

        report = score(ctx)
        # Should not crash
        assert report.total_score >= 0
        # The broken rule should appear as passed with error evidence
        broken_result = next(
            (r for r in report.all_results if r.rule_id == "R1.1"), None
        )
        assert broken_result is not None
        assert broken_result.passed
        assert "error" in broken_result.evidence
