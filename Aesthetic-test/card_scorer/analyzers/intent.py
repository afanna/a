"""Intent Classifier and Entity Matching.

Classifies user query intents and verifies if expected entities
appear in the OCR text. Uses rule-based matching for stability
and interpretability -- no ML models or LLM calls needed.

Based on: INTENT_MATCHING.md
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Pattern


class IntentType(Enum):
    """Supported intent types (Phase 1 + 2)."""
    WEATHER = auto()       # 天气查询
    SCHEDULE = auto()      # 日程/日历
    TODO = auto()          # 待办事项
    NEWS = auto()          # 新闻
    STOCK = auto()         # 股票/基金
    COUNTDOWN = auto()     # 倒计时
    HEALTH = auto()        # 健康数据
    MUSIC = auto()         # 音乐
    AUDIO_DEVICE = auto()  # 音频设备（耳机、音箱等）
    NOTIFICATION = auto()  # 通知
    GENERAL = auto()       # 通用/其他


@dataclass
class EntityPattern:
    """Pattern to detect an entity type in OCR text."""
    name: str
    pattern: Pattern[str]
    description: str = ""
    is_required: bool = False  # Is this a required entity?


@dataclass
class IntentConfig:
    """Configuration for an intent type."""
    intent: IntentType
    trigger_keywords: list[str]  # Trigger keywords for this intent
    entity_patterns: list[EntityPattern]  # Entity patterns
    keyword_weights: dict[str, float] | None = None  # Optional weights

    def get_score(self, query: str) -> float:
        """Calculate match score for this intent against query."""
        score = 0.0
        for kw in self.trigger_keywords:
            if kw in query:
                weight = 1.0
                if self.keyword_weights and kw in self.keyword_weights:
                    weight = self.keyword_weights[kw]
                score += weight
        return score


def _compile(pattern: str) -> Pattern[str]:
    """Compile regex pattern with IGNORECASE."""
    return re.compile(pattern, re.IGNORECASE)


# --- Entity Pattern Definitions ---

WEATHER_ENTITIES = [
    EntityPattern(
        name="temperature",
        pattern=_compile(r'\d{1,2}\s*[°℃度]|\b\d{1,2}\s*(?:度|°)\s*[CF]?|\b([3-5]\d)\b'),
        description="温度值 (25°C, 30度)",
        is_required=True,
    ),
    EntityPattern(
        name="weather_condition",
        pattern=_compile(r'(?:晴|阴|多[云天]|小[雨雪]|中[雨雪]|大[雨雪]|暴[雨雪]|雷阵雨|雾霾|大风|沙尘)'),
        description="天气状况",
        is_required=False,
    ),
    EntityPattern(
        name="location",
        pattern=_compile(r'[一-龥]{2,6}(?:市|区|县|省)?'),
        description="地点名",
        is_required=False,
    ),
    EntityPattern(
        name="date",
        pattern=_compile(r'(?:今天|明天|后天|周[一二三四五六日]|本周|下周|\d{1,2}月\d{1,2}日)'),
        description="日期/时间",
        is_required=False,
    ),
    EntityPattern(
        name="humidity",
        pattern=_compile(r'湿度\s*[:：]?\s*\d{1,3}%'),
        description="湿度",
        is_required=False,
    ),
    EntityPattern(
        name="wind",
        pattern=_compile(r'(?:东|南|西|北|东南|东北|西南|西北)风|\d+级'),
        description="风向风力",
        is_required=False,
    ),
]

SCHEDULE_ENTITIES = [
    EntityPattern(
        name="time",
        pattern=_compile(r'\d{1,2}[:：]\d{2}|\d{1,2}\s*[点时]\s*\d{0,2}'),
        description="时间点 (14:30, 3点)",
        is_required=True,
    ),
    EntityPattern(
        name="title",
        pattern=_compile(r'[一-龥a-zA-Z]{2,30}'),
        description="标题/事件名",
        is_required=True,
    ),
    EntityPattern(
        name="date",
        pattern=_compile(r'(?:今天|明天|后天|周[一二三四五六日]|\d{1,2}月\d{1,2}日)'),
        description="日期",
        is_required=False,
    ),
    EntityPattern(
        name="location",
        pattern=_compile(r'(?:会议室|腾讯会议|Zoom|Teams|[一-龥]{2,10})'),
        description="会议地点",
        is_required=False,
    ),
]

TODO_ENTITIES = [
    EntityPattern(
        name="task",
        pattern=_compile(r'[一-龥a-zA-Z0-9]{2,50}'),
        description="任务内容",
        is_required=True,
    ),
    EntityPattern(
        name="progress",
        pattern=_compile(r'\d+%'),
        description="进度百分比",
        is_required=False,
    ),
    EntityPattern(
        name="status",
        pattern=_compile(r'(?:待完成|进行中|已完成|已过期)'),
        description="任务状态",
        is_required=False,
    ),
]

NEWS_ENTITIES = [
    EntityPattern(
        name="title",
        pattern=_compile(r'[一-龥a-zA-Z0-9]{5,100}'),
        description="标题/内容",
        is_required=True,
    ),
    EntityPattern(
        name="source",
        pattern=_compile(r'(?:来源|来自|发布|记者|编辑)'),
        description="来源信息",
        is_required=False,
    ),
]

STOCK_ENTITIES = [
    EntityPattern(
        name="price",
        pattern=_compile(r'[¥$€]?\s*\d+(?:\.\d+)?|\d+(?:\.\d+)?\s*[元块美元欧元]?'),
        description="价格",
        is_required=True,
    ),
    EntityPattern(
        name="change",
        pattern=_compile(r'[+-]\s*\d+(?:\.\d+)?%?|(?:涨|跌|上涨|下跌|涨幅|跌幅)'),
        description="涨跌幅",
        is_required=True,
    ),
    EntityPattern(
        name="stock_name",
        pattern=_compile(r'[一-龥]{2,6}(?:股|科技|医疗|银行|能源)?'),
        description="股票名称",
        is_required=False,
    ),
]

COUNTDOWN_ENTITIES = [
    EntityPattern(
        name="days",
        pattern=_compile(r'\d+\s*天'),
        description="剩余天数",
        is_required=True,
    ),
    EntityPattern(
        name="target",
        pattern=_compile(r'[一-龥a-zA-Z0-9]{2,30}'),
        description="倒计时目标",
        is_required=False,
    ),
]

HEALTH_ENTITIES = [
    EntityPattern(
        name="steps",
        pattern=_compile(r'\d{3,6}\s*步'),
        description="步数",
        is_required=False,
    ),
    EntityPattern(
        name="heart_rate",
        pattern=_compile(r'\d{2,3}\s*bpm|\d{2,3}\s*次/分'),
        description="心率",
        is_required=False,
    ),
    EntityPattern(
        name="sleep",
        pattern=_compile(r'\d+小时\d*分钟?'),
        description="睡眠时长",
        is_required=False,
    ),
    EntityPattern(
        name="calories",
        pattern=_compile(r'\d+\s*千卡?'),
        description="卡路里",
        is_required=False,
    ),
]

AUDIO_DEVICE_ENTITIES = [
    EntityPattern(
        name="device_name",
        pattern=_compile(r'[A-Za-z][A-Za-z0-9\s]{4,30}|[一-龥]{3,10}(?:耳机|音箱|设备|蓝牙)'),
        description="设备名称（至少5个字符）",
        is_required=True,
    ),
    EntityPattern(
        name="battery_level",
        pattern=_compile(r'(?:左|L|右|R)[一-龥\s]*[:：]?\s*\d{1,3}\s*%|\d{1,3}\s*%.*?\d{1,3}\s*%'),
        description="电量（需包含左右标识或两个百分比）",
        is_required=True,
    ),
    EntityPattern(
        name="connection_status",
        pattern=_compile(r'(?:已连接|未连接|连接中|已配对|断开)'),
        description="连接状态",
        is_required=False,
    ),
    EntityPattern(
        name="playlist_or_control",
        pattern=_compile(r'(?:播放列表|歌单|音乐|播放|暂停|上一曲|下一曲|[一-龥]{2,10}(?:首|曲))'),
        description="播放控制或歌单",
        is_required=False,
    ),
]

GENERAL_ENTITIES = [
    EntityPattern(
        name="any_text",
        pattern=_compile(r'[一-龥a-zA-Z0-9]{2,}'),
        description="任何有意义的文本",
        is_required=True,
    ),
]


# --- Intent Configurations ---

INTENT_CONFIGS: list[IntentConfig] = [
    # Phase 1: High coverage
    IntentConfig(
        intent=IntentType.WEATHER,
        trigger_keywords=["天气", "气温", "温度", "预报", "降雨", "空气质量"],
        entity_patterns=WEATHER_ENTITIES,
        keyword_weights={"天气": 2.0, "气温": 1.5, "预报": 1.5},
    ),
    IntentConfig(
        intent=IntentType.SCHEDULE,
        trigger_keywords=["会议", "日程", "安排", "行程", "提醒", "日历", "预约", "约会"],
        entity_patterns=SCHEDULE_ENTITIES,
        keyword_weights={"会议": 2.0, "日程": 2.0},
    ),
    IntentConfig(
        intent=IntentType.TODO,
        trigger_keywords=["待办", "任务", "事项", "计划", "清单", "todo"],
        entity_patterns=TODO_ENTITIES,
        keyword_weights={"待办": 2.0, "任务": 2.0},
    ),
    # Phase 2: Additional coverage
    IntentConfig(
        intent=IntentType.NEWS,
        trigger_keywords=["新闻", "资讯", "头条", "消息", "报道"],
        entity_patterns=NEWS_ENTITIES,
    ),
    IntentConfig(
        intent=IntentType.STOCK,
        trigger_keywords=["股票", "股价", "行情", "涨跌", "基金", "理财"],
        entity_patterns=STOCK_ENTITIES,
    ),
    IntentConfig(
        intent=IntentType.COUNTDOWN,
        trigger_keywords=["倒计时", "还有", "距离", "剩余"],
        entity_patterns=COUNTDOWN_ENTITIES,
    ),
    IntentConfig(
        intent=IntentType.HEALTH,
        trigger_keywords=["步数", "睡眠", "心率", "运动", "健康", "卡路里"],
        entity_patterns=HEALTH_ENTITIES,
    ),
    IntentConfig(
        intent=IntentType.AUDIO_DEVICE,
        trigger_keywords=["耳机", "音箱", "蓝牙", "设备", "电量", "连接", "播放", "歌单", "音乐"],
        entity_patterns=AUDIO_DEVICE_ENTITIES,
        keyword_weights={"耳机": 2.0, "电量": 1.5, "歌单": 1.5, "音箱": 2.0},
    ),
    # Fallback: always last
    IntentConfig(
        intent=IntentType.GENERAL,
        trigger_keywords=[],
        entity_patterns=GENERAL_ENTITIES,
    ),
]


@dataclass
class IntentMatchResult:
    """Result of intent classification and entity matching."""
    intent: IntentType
    confidence: float = 0.0
    matched_keywords: list[str] = field(default_factory=list)
    matched_entities: list[dict[str, Any]] = field(default_factory=list)
    missing_required_entities: list[str] = field(default_factory=list)
    has_required_entities: bool = False
    all_text_has_content: bool = False  # For GENERAL fallback

    @property
    def intent_name(self) -> str:
        """Get human-readable intent name."""
        return self.intent.name

    def to_dict(self) -> dict[str, Any]:
        """Convert to serializable dict."""
        return {
            "intent": self.intent_name,
            "confidence": self.confidence,
            "matched_keywords": self.matched_keywords,
            "matched_entities": self.matched_entities,
            "missing_required_entities": self.missing_required_entities,
            "has_required_entities": self.has_required_entities,
        }


class IntentClassifier:
    """Rule-based intent classifier with entity matching."""

    def __init__(self) -> None:
        self.configs = INTENT_CONFIGS

    def classify(self, query: str) -> IntentMatchResult:
        """Classify query intent based on keyword matching with scoring."""
        if not query.strip():
            return IntentMatchResult(
                intent=IntentType.GENERAL,
                confidence=1.0
            )

        best_config: IntentConfig | None = None
        best_score = 0.0
        matched_kws: list[str] = []

        for config in self.configs:
            if not config.trigger_keywords and best_config is not None:
                continue  # Skip GENERAL until end

            score = config.get_score(query)
            if score > best_score:
                best_score = score
                best_config = config
                matched_kws = [kw for kw in config.trigger_keywords if kw in query]

        # Use GENERAL if no specific match
        if best_config is None or best_score == 0:
            best_config = self.configs[-1]  # Last is GENERAL
            confidence = 0.5
        else:
            confidence = min(1.0, best_score / 2.0)  # Normalize to [0,1]

        return IntentMatchResult(
            intent=best_config.intent,
            confidence=confidence,
            matched_keywords=matched_kws
        )

    def match_entities(
        self,
        ocr_texts: list[str],
        intent_result: IntentMatchResult
    ) -> IntentMatchResult:
        """Match entities from OCR text based on intent."""
        all_text = " ".join(ocr_texts)

        # Find config for this intent
        config = next(
            (c for c in self.configs if c.intent == intent_result.intent),
            None
        )

        if not config:
            # Fallback: just check if there's any meaningful content
            intent_result.has_required_entities = len(ocr_texts) > 0
            intent_result.all_text_has_content = len(ocr_texts) > 0
            return intent_result

        matched = []
        required_found = []

        for pattern in config.entity_patterns:
            matches = pattern.pattern.findall(all_text)
            if matches:
                # Deduplicate and limit
                unique_matches = list(dict.fromkeys(matches))[:3]
                matched.append({
                    "type": pattern.name,
                    "matches": unique_matches,
                    "description": pattern.description,
                    "is_required": pattern.is_required,
                })
                if pattern.is_required:
                    required_found.append(pattern.name)

        intent_result.matched_entities = matched

        # Check required entities
        required_names = [p.name for p in config.entity_patterns if p.is_required]

        # Special logic for WEATHER: temperature + (condition OR location)
        if config.intent == IntentType.WEATHER:
            has_temp = any(e["type"] == "temperature" for e in matched)
            has_condition = any(e["type"] == "weather_condition" for e in matched)
            has_location = any(e["type"] == "location" for e in matched)
            intent_result.has_required_entities = has_temp and (has_condition or has_location)
            intent_result.missing_required_entities = []
            if not has_temp:
                intent_result.missing_required_entities.append("temperature")
            if not (has_condition or has_location):
                intent_result.missing_required_entities.append("weather_condition|location")

        # Special logic for SCHEDULE: time + title
        elif config.intent == IntentType.SCHEDULE:
            has_time = any(e["type"] == "time" for e in matched)
            has_title = any(e["type"] == "title" for e in matched)
            intent_result.has_required_entities = has_time and has_title
            intent_result.missing_required_entities = []
            if not has_time:
                intent_result.missing_required_entities.append("time")
            if not has_title:
                intent_result.missing_required_entities.append("title")

        # Special logic for STOCK: price + change
        elif config.intent == IntentType.STOCK:
            has_price = any(e["type"] == "price" for e in matched)
            has_change = any(e["type"] == "change" for e in matched)
            intent_result.has_required_entities = has_price and has_change
            intent_result.missing_required_entities = []
            if not has_price:
                intent_result.missing_required_entities.append("price")
            if not has_change:
                intent_result.missing_required_entities.append("change")

        # Special logic for AUDIO_DEVICE: device_name + battery_level
        elif config.intent == IntentType.AUDIO_DEVICE:
            has_device_name = any(e["type"] == "device_name" for e in matched)
            has_battery = any(e["type"] == "battery_level" for e in matched)
            intent_result.has_required_entities = has_device_name and has_battery
            intent_result.missing_required_entities = []
            if not has_device_name:
                intent_result.missing_required_entities.append("device_name")
            if not has_battery:
                intent_result.missing_required_entities.append("battery_level")

        # General case: check if all required entities are found
        else:
            missing = [n for n in required_names if n not in required_found]
            intent_result.missing_required_entities = missing
            intent_result.has_required_entities = len(missing) == 0

        # Check if there's any content at all (for fallback scoring)
        intent_result.all_text_has_content = len([t for t in ocr_texts if t.strip()]) > 0

        return intent_result

    def analyze(self, query: str, ocr_texts: list[str]) -> IntentMatchResult:
        """Full analysis: classify intent + match entities."""
        result = self.classify(query)
        return self.match_entities(ocr_texts, result)


# Singleton instance
_classifier: IntentClassifier | None = None


def get_classifier() -> IntentClassifier:
    """Get the singleton intent classifier instance."""
    global _classifier
    if _classifier is None:
        _classifier = IntentClassifier()
    return _classifier
