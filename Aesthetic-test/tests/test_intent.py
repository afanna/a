"""Tests for Intent Classifier."""

import pytest

from card_scorer.analyzers.intent import IntentClassifier, IntentType


class TestIntentClassification:
    """Tests for intent classification."""

    def test_classify_weather(self):
        """Should classify weather queries."""
        clf = IntentClassifier()
        result = clf.classify("显示当地天气情况")
        assert result.intent == IntentType.WEATHER
        assert "天气" in result.matched_keywords

    def test_classify_schedule(self):
        """Should classify schedule queries."""
        clf = IntentClassifier()
        result = clf.classify("明天的会议安排")
        assert result.intent == IntentType.SCHEDULE

    def test_classify_todo(self):
        """Should classify todo queries."""
        clf = IntentClassifier()
        result = clf.classify("查看我的待办任务")
        assert result.intent == IntentType.TODO

    def test_classify_general(self):
        """Should classify unknown queries as GENERAL."""
        clf = IntentClassifier()
        result = clf.classify("随便看看")
        assert result.intent == IntentType.GENERAL

    def test_classify_empty_query(self):
        """Should handle empty query."""
        clf = IntentClassifier()
        result = clf.classify("")
        assert result.intent == IntentType.GENERAL

    def test_classify_stock(self):
        """Should classify stock queries."""
        clf = IntentClassifier()
        result = clf.classify("今日股价行情")
        assert result.intent == IntentType.STOCK

    def test_classify_health(self):
        """Should classify health queries."""
        clf = IntentClassifier()
        result = clf.classify("今天的运动步数")
        assert result.intent == IntentType.HEALTH


class TestEntityMatching:
    """Tests for entity matching."""

    def test_weather_entity_match(self):
        """Should match weather entities."""
        clf = IntentClassifier()
        intent_result = clf.classify("今天天气")
        result = clf.match_entities(["25°C", "上海", "晴"], intent_result)
        assert result.has_required_entities
        assert len(result.matched_entities) >= 1
        assert any(e["type"] == "temperature" for e in result.matched_entities)

    def test_weather_entity_temperature_only(self):
        """Temperature alone is not enough for weather."""
        clf = IntentClassifier()
        intent_result = clf.classify("今天天气")
        result = clf.match_entities(["25°C"], intent_result)
        assert not result.has_required_entities  # Needs temp + condition/location

    def test_weather_entity_complete(self):
        """Temperature + condition should pass weather check."""
        clf = IntentClassifier()
        intent_result = clf.classify("今天天气")
        result = clf.match_entities(["25°C", "晴"], intent_result)
        assert result.has_required_entities

    def test_schedule_entity_match(self):
        """Should match schedule entities."""
        clf = IntentClassifier()
        intent_result = clf.classify("明天会议")
        result = clf.match_entities(["14:00", "团队会议"], intent_result)
        assert result.has_required_entities

    def test_schedule_entity_missing_time(self):
        """Missing time should fail schedule check."""
        clf = IntentClassifier()
        intent_result = clf.classify("明天会议")
        result = clf.match_entities(["团队会议"], intent_result)
        assert not result.has_required_entities
        assert "time" in result.missing_required_entities

    def test_stock_entity_match(self):
        """Should match stock entities."""
        clf = IntentClassifier()
        intent_result = clf.classify("股票行情")
        result = clf.match_entities(["123.45", "+2.5%"], intent_result)
        assert result.has_required_entities

    def test_general_fallback_has_content(self):
        """General intent should pass if there's any content."""
        clf = IntentClassifier()
        intent_result = clf.classify("随便看看")
        result = clf.match_entities(["一些内容"], intent_result)
        assert result.all_text_has_content

    def test_full_analysis(self):
        """Full analysis should work end-to-end."""
        clf = IntentClassifier()
        result = clf.analyze("显示当地天气情况", ["25°C", "上海", "晴"])
        assert result.intent == IntentType.WEATHER
        assert result.has_required_entities

    def test_to_dict(self):
        """Result should be serializable to dict."""
        clf = IntentClassifier()
        result = clf.analyze("今天天气", ["25°C", "晴"])
        d = result.to_dict()
        assert "intent" in d
        assert "matched_entities" in d
        assert "has_required_entities" in d


class TestRealWorldScenarios:
    """Tests for real-world scenarios from the design doc."""

    def test_weather_scenario_from_design_doc(self):
        """The exact scenario from INTENT_MATCHING.md should pass."""
        clf = IntentClassifier()
        query = "显示当地天气情况"
        ocr_texts = ["25°C", "上海", "晴"]
        result = clf.analyze(query, ocr_texts)
        assert result.intent == IntentType.WEATHER
        assert result.has_required_entities

    def test_schedule_scenario(self):
        """Schedule scenario should work."""
        clf = IntentClassifier()
        query = "明天的会议"
        ocr_texts = ["14:00", "团队会议", "会议室A"]
        result = clf.analyze(query, ocr_texts)
        assert result.intent == IntentType.SCHEDULE
        assert result.has_required_entities

    def test_todo_scenario(self):
        """Todo scenario should work."""
        clf = IntentClassifier()
        query = "我的待办清单"
        ocr_texts = ["完成报告", "80%"]
        result = clf.analyze(query, ocr_texts)
        assert result.intent == IntentType.TODO
        assert result.has_required_entities
