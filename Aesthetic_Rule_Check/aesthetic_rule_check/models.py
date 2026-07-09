from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def x2(self) -> float:
        return self.x + self.width

    @property
    def y2(self) -> float:
        return self.y + self.height

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.width / 2.0, self.y + self.height / 2.0)


@dataclass(frozen=True)
class TextBlock:
    text: str
    bbox: Rect
    confidence: float
    font_size: float
    contrast_ratio: float | None = None


@dataclass(frozen=True)
class VisualElement:
    kind: str
    bbox: Rect
    confidence: float = 1.0
    text: str | None = None
    color: tuple[int, int, int] | None = None
    layer: int = 1
    radius: float | None = None
    style_features: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VisionContext:
    image_path: Path
    width: int
    height: int
    card_bbox: Rect
    text_blocks: list[TextBlock]
    elements: list[VisualElement]
    dominant_colors: list[tuple[int, int, int]]
    color_proportions: list[float]
    confidence: float


@dataclass(frozen=True)
class RequiredText:
    text: str
    source: str
    component_id: str | None = None


@dataclass(frozen=True)
class DslInfo:
    path: Path | None
    required_texts: list[RequiredText]
    data_model: dict[str, Any]
    component_count: int
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MetricResult:
    name: str
    dimension: str
    score: float | None
    value: Any = None
    ideal: Any = None
    deviation: Any = None
    confidence: float = 1.0
    formula: str = ""
    status: str = "ok"
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DimensionResult:
    name: str
    label: str
    score: float
    weight: float
    metrics: list[MetricResult]


@dataclass(frozen=True)
class EvaluationResult:
    image_path: Path
    dsl_path: Path | None
    query: str
    overall: float
    grade: str
    confidence: float
    dimensions: list[DimensionResult]
    metrics: list[MetricResult]
    required_texts: list[RequiredText]
    missing_texts: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return to_plain(self)


def to_plain(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return {key: to_plain(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): to_plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_plain(item) for item in value]
    return value
