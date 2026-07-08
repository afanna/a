"""Tests for structure rules (DSL-based)."""

import pytest

from card_scorer.models import BBox, ScoringContext
from card_scorer.rules.structure import (
    NestingDepthRule,
    EmptyContainerRule,
    BorderRadiusConsistencyRule,
    ExcessiveDecorationRule,
)


def _ctx(dsl_tree=None):
    return ScoringContext(dsl_tree=dsl_tree)


class TestNestingDepthRule:
    def test_no_dsl(self):
        ctx = _ctx()
        result = NestingDepthRule().evaluate(ctx)
        assert result.passed is True

    def test_shallow(self):
        ctx = _ctx({"type": "root", "children": [{"type": "text"}]})
        result = NestingDepthRule().evaluate(ctx)
        assert result.passed is True

    def test_too_deep(self):
        ctx = _ctx({
            "type": "root",
            "children": [{
                "type": "container",
                "children": [{
                    "type": "container",
                    "children": [{
                        "type": "container",
                        "children": [{
                            "type": "container",
                            "children": [{
                                "type": "container",
                                "children": [{"type": "text"}]
                            }]
                        }]
                    }]
                }]
            }]
        })
        result = NestingDepthRule().evaluate(ctx)
        assert result.passed is False


class TestEmptyContainerRule:
    def test_no_dsl(self):
        ctx = _ctx()
        result = EmptyContainerRule().evaluate(ctx)
        assert result.passed is True

    def test_no_empty(self):
        ctx = _ctx({
            "type": "root",
            "children": [{"type": "text"}]
        })
        result = EmptyContainerRule().evaluate(ctx)
        assert result.passed is True

    def test_empty_found(self):
        ctx = _ctx({
            "type": "root",
            "children": [{"type": "container", "children": []}]
        })
        result = EmptyContainerRule().evaluate(ctx)
        assert result.passed is False


class TestBorderRadiusConsistencyRule:
    def test_no_dsl(self):
        ctx = _ctx()
        result = BorderRadiusConsistencyRule().evaluate(ctx)
        assert result.passed is True

    def test_few_levels(self):
        ctx = _ctx({
            "type": "root",
            "children": [
                {"type": "card", "borderRadius": 8},
                {"type": "button", "borderRadius": 8},
            ]
        })
        result = BorderRadiusConsistencyRule().evaluate(ctx)
        assert result.passed is True

    def test_too_many_levels(self):
        ctx = _ctx({
            "type": "root",
            "children": [
                {"type": "card", "borderRadius": 4},
                {"type": "card", "borderRadius": 8},
                {"type": "card", "borderRadius": 12},
                {"type": "card", "borderRadius": 16},
            ]
        })
        result = BorderRadiusConsistencyRule().evaluate(ctx)
        assert result.passed is False


class TestExcessiveDecorationRule:
    def test_no_dsl(self):
        ctx = _ctx()
        result = ExcessiveDecorationRule().evaluate(ctx)
        assert result.passed is True

    def test_few_decorations(self):
        ctx = _ctx({
            "type": "root",
            "children": [{"type": "text"}]
        })
        result = ExcessiveDecorationRule().evaluate(ctx)
        assert result.passed is True

    def test_too_many_decorations(self):
        ctx = _ctx({
            "type": "root",
            "children": [
                {"type": "decoration"},
                {"type": "divider"},
                {"type": "separator"},
                {"type": "ornament"},
            ]
        })
        result = ExcessiveDecorationRule().evaluate(ctx)
        assert result.passed is False
