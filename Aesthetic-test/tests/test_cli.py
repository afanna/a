"""Integration tests for CLI (card_scorer.cli.main).

Covers:
- CLI invocation with minimal args
- CLI invocation with all args
- Output file generation
- Error handling for missing image
- Exit codes for PASS/FAIL
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import pytest
from typer.testing import CliRunner

from card_scorer.cli.main import app
from card_scorer.configs.loader import Config


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reload_config() -> None:
    Config.reload()


@pytest.fixture
def runner() -> CliRunner:
    """Typer CLI test runner."""
    return CliRunner()


@pytest.fixture
def test_image() -> str:
    """Create a temporary test image."""
    img = np.full((200, 300, 3), 255, dtype=np.uint8)
    # Add some text-like content
    cv2.rectangle(img, (20, 20), (100, 50), (30, 30, 30), -1)
    cv2.rectangle(img, (20, 60), (150, 90), (30, 30, 30), -1)
    with tempfile.NamedTemporaryFile(
        suffix=".png", delete=False
    ) as f:
        cv2.imwrite(f.name, img)
        return f.name


@pytest.fixture
def test_dsl() -> str:
    """Create a temporary DSL JSON file."""
    dsl = {"type": "Column", "children": [
        {"type": "Text", "content": "Hello"},
        {"type": "Text", "content": "World"},
    ]}
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(dsl, f)
        return f.name


# ---------------------------------------------------------------------------
# CLI Tests
# ---------------------------------------------------------------------------

class TestCliBasic:
    """Basic CLI invocation tests."""

    def test_help(self, runner: CliRunner) -> None:
        """--help should work."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Score a card screenshot" in result.stdout

    def test_missing_image(self, runner: CliRunner) -> None:
        """Missing --image should error."""
        result = runner.invoke(app, ["--query", "test"])
        assert result.exit_code != 0

    def test_nonexistent_image(self, runner: CliRunner) -> None:
        """Nonexistent image path should error."""
        result = runner.invoke(app, [
            "--image", "/nonexistent/path.png",
            "--query", "test",
        ])
        assert result.exit_code != 0


class TestCliScoring:
    """End-to-end scoring via CLI."""

    def test_score_with_image_and_query(
        self, runner: CliRunner, test_image: str
    ) -> None:
        """Basic scoring with image and query."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.invoke(app, [
                "--image", test_image,
                "--query", "测试天气",
                "--output", tmpdir,
            ])
            # May exit 0 (PASS) or 1 (FAIL), both are valid
            assert result.exit_code in (0, 1)
            assert "Card Score:" in result.stdout
            assert "Status:" in result.stdout

    def test_score_generates_json_report(
        self, runner: CliRunner, test_image: str
    ) -> None:
        """Scoring should generate a JSON report."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runner.invoke(app, [
                "--image", test_image,
                "--query", "测试",
                "--output", tmpdir,
            ])
            json_path = os.path.join(tmpdir, "report.json")
            assert os.path.exists(json_path), f"JSON report not found at {json_path}"
            with open(json_path, encoding="utf-8") as f:
                data = json.load(f)
            assert "total_score" in data
            assert "status" in data

    def test_score_generates_html_report(
        self, runner: CliRunner, test_image: str
    ) -> None:
        """Scoring should generate an HTML report."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runner.invoke(app, [
                "--image", test_image,
                "--query", "测试",
                "--output", tmpdir,
            ])
            html_path = os.path.join(tmpdir, "report.html")
            assert os.path.exists(html_path), f"HTML report not found at {html_path}"
            content = Path(html_path).read_text(encoding="utf-8")
            assert "<html" in content.lower()

    def test_score_with_dsl(
        self, runner: CliRunner, test_image: str, test_dsl: str
    ) -> None:
        """Scoring with DSL should work."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.invoke(app, [
                "--image", test_image,
                "--query", "测试",
                "--dsl", test_dsl,
                "--output", tmpdir,
            ])
            assert result.exit_code in (0, 1)

    def test_score_verbose(
        self, runner: CliRunner, test_image: str
    ) -> None:
        """Verbose mode should not crash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.invoke(app, [
                "--image", test_image,
                "--query", "测试",
                "--output", tmpdir,
                "--verbose",
            ])
            assert result.exit_code in (0, 1)

    def test_score_output_contains_top_issues(
        self, runner: CliRunner, test_image: str
    ) -> None:
        """Output should list top issues when deductions exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.invoke(app, [
                "--image", test_image,
                "--query", "测试天气",
                "--output", tmpdir,
            ])
            # Should have either "Top Issues" or "No issues detected"
            assert (
                "Top Issues" in result.stdout
                or "No issues" in result.stdout
            )

    def test_score_report_json_has_dimensions(
        self, runner: CliRunner, test_image: str
    ) -> None:
        """JSON report should contain dimension breakdown."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runner.invoke(app, [
                "--image", test_image,
                "--query", "测试",
                "--output", tmpdir,
            ])
            json_path = os.path.join(tmpdir, "report.json")
            with open(json_path, encoding="utf-8") as f:
                data = json.load(f)
            assert "dimensions" in data
            assert len(data["dimensions"]) >= 1

    def test_score_report_json_has_metadata(
        self, runner: CliRunner, test_image: str
    ) -> None:
        """JSON report should contain metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runner.invoke(app, [
                "--image", test_image,
                "--query", "测试",
                "--output", tmpdir,
            ])
            json_path = os.path.join(tmpdir, "report.json")
            with open(json_path, encoding="utf-8") as f:
                data = json.load(f)
            assert "metadata" in data
            assert "image_path" in data["metadata"]
