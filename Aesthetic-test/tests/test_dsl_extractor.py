"""Tests for DSL extractor."""

import json
import tempfile
from pathlib import Path

from card_scorer.extractors.dsl_extractor import (
    load_dsl,
    get_max_nesting_depth,
    find_empty_containers,
)


class TestLoadDsl:
    def test_empty_path(self):
        assert load_dsl("") is None

    def test_nonexistent(self):
        assert load_dsl("/nonexistent/path.json") is None

    def test_valid_json(self, tmp_path):
        p = tmp_path / "test.json"
        p.write_text('{"type": "container", "children": []}', encoding="utf-8")
        result = load_dsl(str(p))
        assert result is not None
        assert result["type"] == "container"


class TestNestingDepth:
    def test_flat(self):
        tree = {"type": "root"}
        assert get_max_nesting_depth(tree) == 0

    def test_nested(self):
        tree = {"type": "root", "children": [{"type": "child", "children": [{"type": "leaf"}]}]}
        assert get_max_nesting_depth(tree) == 2


class TestEmptyContainers:
    def test_no_empty(self):
        tree = {"type": "root", "children": [{"type": "text"}]}
        assert find_empty_containers(tree) == []

    def test_empty_found(self):
        tree = {"type": "root", "children": [{"type": "container", "children": []}]}
        result = find_empty_containers(tree)
        assert len(result) == 1
