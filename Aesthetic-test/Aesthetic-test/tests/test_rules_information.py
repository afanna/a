"""Tests for information completeness rules."""

import pytest

from card_scorer.models import BBox, ScoringContext, TextElement
from card_scorer.rules.information import (
    KeywordMissingRule,
    TextTruncationRule,
    InformationRedundancyRule,
    EntityMissingRule,
)


def _ctx(query="", texts=None, keywords=None):
    return ScoringContext(
        query=query,
        text_elements=texts or [],
        keywords=keywords or [],
    )


def _text(x1, y1, x2, y2, text="t", confidence=0.99):
    return TextElement(text=text, bbox=BBox(x1, y1, x2, y2), confidence=confidence)


class TestKeywordMissingRule:
    def test_weather_all_required_found(self):
        ctx = _ctx(
            query="深圳天气",
            texts=[_text(0, 0, 100, 20, "25°C"), _text(0, 30, 100, 50, "晴")],
            keywords=["深圳", "天气"],
        )
        result = KeywordMissingRule().evaluate(ctx)
        assert result.passed is True
        assert result.score_delta == 0.0
        assert result.evidence["intent"] == "WEATHER"

    def test_weather_missing_temperature(self):
        ctx = _ctx(
            query="深圳天气",
            texts=[_text(0, 0, 100, 20, "晴")],
            keywords=["深圳", "天气"],
        )
        result = KeywordMissingRule().evaluate(ctx)
        assert result.passed is False
        assert result.score_delta < 0
        assert "temperature" in result.evidence["missing_required_entities"]

    def test_schedule_all_found(self):
        ctx = _ctx(
            query="明天会议",
            texts=[_text(0, 0, 100, 20, "14:00"), _text(0, 30, 100, 50, "团队会议")],
        )
        result = KeywordMissingRule().evaluate(ctx)
        assert result.passed is True
        assert result.evidence["intent"] == "SCHEDULE"

    def test_no_keywords_general(self):
        ctx = _ctx(texts=[_text(0, 0, 100, 20, "hello world")])
        result = KeywordMissingRule().evaluate(ctx)
        assert result.passed is True

    def test_general_has_content(self):
        ctx = _ctx(
            query="随便看看",
            texts=[_text(0, 0, 100, 20, "一些内容")],
        )
        result = KeywordMissingRule().evaluate(ctx)
        assert result.passed is True

    def test_no_content_at_all(self):
        ctx = _ctx(query="显示内容")
        result = KeywordMissingRule().evaluate(ctx)
        assert result.passed is False


class TestTextTruncationRule:
    def test_no_truncation(self):
        ctx = _ctx(texts=[_text(0, 0, 100, 20, "完整文本", confidence=0.95)])
        result = TextTruncationRule().evaluate(ctx)
        assert result.passed is True

    def test_low_confidence(self):
        ctx = _ctx(texts=[_text(0, 0, 100, 20, "模糊文本", confidence=0.3)])
        result = TextTruncationRule().evaluate(ctx)
        assert result.passed is False
        assert result.score_delta < 0

    def test_ellipsis(self):
        ctx = _ctx(texts=[_text(0, 0, 100, 20, "截断文本...", confidence=0.95)])
        result = TextTruncationRule().evaluate(ctx)
        assert result.passed is False

    def test_empty_texts(self):
        ctx = _ctx()
        result = TextTruncationRule().evaluate(ctx)
        assert result.passed is True


class TestInformationRedundancyRule:
    def test_no_duplicates(self):
        ctx = _ctx(texts=[
            _text(0, 0, 100, 20, "hello"),
            _text(0, 30, 100, 50, "world"),
        ])
        result = InformationRedundancyRule().evaluate(ctx)
        assert result.passed is True

    def test_duplicate_found(self):
        ctx = _ctx(texts=[
            _text(0, 0, 100, 20, "hello world"),
            _text(0, 30, 100, 50, "hello world"),
        ])
        result = InformationRedundancyRule().evaluate(ctx)
        assert result.passed is False
        assert result.score_delta < 0

    def test_near_duplicate(self):
        ctx = _ctx(texts=[
            _text(0, 0, 100, 20, "hello world"),
            _text(0, 30, 100, 50, "hello worl"),
        ])
        result = InformationRedundancyRule().evaluate(ctx)
        assert result.passed is False

    def test_single_element(self):
        ctx = _ctx(texts=[_text(0, 0, 100, 20, "only one")])
        result = InformationRedundancyRule().evaluate(ctx)
        assert result.passed is True


class TestEntityMissingRule:
    def test_has_text(self):
        ctx = _ctx(texts=[_text(0, 0, 100, 20, "深圳")])
        result = EntityMissingRule().evaluate(ctx)
        assert result.passed is True

    def test_no_text_no_components(self):
        ctx = _ctx()
        result = EntityMissingRule().evaluate(ctx)
        assert result.passed is False
        assert result.score_delta < 0

    def test_no_text_but_has_components(self):
        from card_scorer.models import ComponentElement
        ctx = ScoringContext(
            component_elements=[
                ComponentElement(bbox=BBox(0, 0, 10, 10), area=100, centroid=(5, 5))
            ]
        )
        result = EntityMissingRule().evaluate(ctx)
        assert result.passed is False
        assert result.score_delta < 0
