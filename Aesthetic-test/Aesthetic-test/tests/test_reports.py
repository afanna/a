"""Tests for Report Generators (card_scorer.reports).

Covers:
- JSON report generation and serialization
- HTML report generation with Jinja2
- Report file saving
- Empty report handling
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from card_scorer.configs.loader import Config
from card_scorer.models import (
    DimensionScore,
    RuleResult,
    ScoringReport,
    Severity,
)
from card_scorer.reports.json_report import generate as json_generate, save as json_save
from card_scorer.reports.html_report import generate as html_generate, save as html_save


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reload_config() -> None:
    Config.reload()


@pytest.fixture
def empty_report() -> ScoringReport:
    """Report with no deductions."""
    return ScoringReport(
        total_score=100.0,
        status="PASS",
        fail_triggered=False,
        dimensions=[
            DimensionScore(
                dimension="information",
                dimension_name="信息完整性",
                max_deduction=25,
                actual_deduction=0,
                rule_results=[],
            ),
        ],
        all_results=[],
        deduction_details=[],
        metadata={"image_path": "/tmp/test.png", "query": "test"},
    )


@pytest.fixture
def fail_report() -> ScoringReport:
    """Report with deductions and FAIL status."""
    deductions = [
        RuleResult(
            rule_id="R1.1",
            rule_name="关键词缺失",
            dimension="information",
            passed=False,
            score_delta=-10.0,
            severity=Severity.FATAL,
            evidence={"missing_keywords": ["上海"]},
            explanation="关键词 ['上海'] 未在截图中找到",
            suggestion="检查卡片是否正确渲染了 query 中的关键信息",
        ),
        RuleResult(
            rule_id="VC-1",
            rule_name="对齐一致性",
            dimension="consistency",
            passed=False,
            score_delta=-6.0,
            severity=Severity.MAJOR,
            evidence={"num_left_clusters": 5},
            explanation="检测到 5 条对齐轴线, 离群率 80%",
            suggestion="减少对齐轴线数量",
        ),
    ]
    return ScoringReport(
        total_score=44.0,
        status="FAIL",
        fail_triggered=True,
        dimensions=[
            DimensionScore(
                dimension="information",
                dimension_name="信息完整性",
                max_deduction=25,
                actual_deduction=10,
                rule_results=[deductions[0]],
            ),
            DimensionScore(
                dimension="consistency",
                dimension_name="视觉一致性",
                max_deduction=20,
                actual_deduction=6,
                rule_results=[deductions[1]],
            ),
        ],
        all_results=deductions,
        deduction_details=deductions,
        metadata={
            "image_path": "/tmp/test.png",
            "query": "上海天气",
            "image_size": "400x300",
            "text_count": 2,
            "component_count": 1,
            "color_count": 3,
        },
    )


# ---------------------------------------------------------------------------
# JSON Report
# ---------------------------------------------------------------------------

class TestJsonReport:
    """Tests for JSON report generation."""

    def test_generate_empty_report(self, empty_report: ScoringReport) -> None:
        """Empty report should produce valid JSON structure."""
        data = json_generate(empty_report)
        assert data["total_score"] == 100.0
        assert data["status"] == "PASS"
        assert data["fail_triggered"] is False
        assert isinstance(data["dimensions"], list)
        assert isinstance(data["deductions"], list)

    def test_generate_fail_report(self, fail_report: ScoringReport) -> None:
        """FAIL report should include deduction details."""
        data = json_generate(fail_report)
        assert data["total_score"] == 44.0
        assert data["status"] == "FAIL"
        assert data["fail_triggered"] is True
        assert len(data["deductions"]) == 2
        assert data["deductions"][0]["rule_id"] == "R1.1"
        assert data["deductions"][0]["severity"] == "fatal"

    def test_generate_dimensions_have_rules(self, fail_report: ScoringReport) -> None:
        """Each dimension should contain its rule results."""
        data = json_generate(fail_report)
        for dim in data["dimensions"]:
            assert "rules" in dim
            assert "dimension" in dim
            assert "actual_deduction" in dim

    def test_generate_is_json_serializable(self, fail_report: ScoringReport) -> None:
        """Generated dict should be JSON-serializable."""
        data = json_generate(fail_report)
        dumped = json.dumps(data, ensure_ascii=False)
        reloaded = json.loads(dumped)
        assert reloaded["total_score"] == 44.0

    def test_save_creates_file(self, fail_report: ScoringReport) -> None:
        """save() should create a JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = json_save(fail_report, os.path.join(tmpdir, "report.json"))
            assert os.path.exists(path)
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            assert data["status"] == "FAIL"

    def test_save_creates_parent_dir(self, fail_report: ScoringReport) -> None:
        """save() should create parent directories if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nested = os.path.join(tmpdir, "sub", "deep", "report.json")
            path = json_save(fail_report, nested)
            assert os.path.exists(path)


# ---------------------------------------------------------------------------
# HTML Report
# ---------------------------------------------------------------------------

class TestHtmlReport:
    """Tests for HTML report generation."""

    def test_generate_returns_string(self, empty_report: ScoringReport) -> None:
        """HTML generate should return a string."""
        html = html_generate(empty_report)
        assert isinstance(html, str)
        assert len(html) > 0

    def test_generate_contains_score(self, fail_report: ScoringReport) -> None:
        """HTML should contain the total score."""
        html = html_generate(fail_report)
        assert "44" in html or "44.0" in html

    def test_generate_contains_status(self, fail_report: ScoringReport) -> None:
        """HTML should contain PASS or FAIL."""
        html = html_generate(fail_report)
        assert "FAIL" in html

    def test_generate_contains_rule_ids(self, fail_report: ScoringReport) -> None:
        """HTML should reference rule IDs."""
        html = html_generate(fail_report)
        assert "R1.1" in html
        assert "VC-1" in html

    def test_generate_no_image_does_not_crash(self, empty_report: ScoringReport) -> None:
        """HTML generation should work without an image."""
        html = html_generate(empty_report, image_path="")
        assert isinstance(html, str)

    def test_generate_with_nonexistent_image(self, fail_report: ScoringReport) -> None:
        """HTML generation should handle nonexistent image path gracefully."""
        html = html_generate(fail_report, image_path="/nonexistent/path.png")
        assert isinstance(html, str)

    def test_save_creates_html_file(self, fail_report: ScoringReport) -> None:
        """save() should create an HTML file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = html_save(fail_report, os.path.join(tmpdir, "report.html"))
            assert os.path.exists(path)
            content = Path(path).read_text(encoding="utf-8")
            assert "<html" in content.lower()
            assert "FAIL" in content

    def test_empty_report_html_no_issues(self, empty_report: ScoringReport) -> None:
        """Empty report HTML should indicate no issues."""
        html = html_generate(empty_report)
        assert "No Issues" in html or "no issues" in html.lower() or "All rules passed" in html
