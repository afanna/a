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
class DslComponentBox:
    component_id: str
    component_type: str
    bbox: Rect
    font_size: float | None = None
    text: str | None = None
    styles: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DslInfo:
    path: Path | None
    required_texts: list[RequiredText]
    data_model: dict[str, Any]
    component_count: int
    components: list[dict[str, Any]] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    root_id: str | None = None
    surface_width: float | None = None
    surface_height: float | None = None
    geometry_boxes: list[DslComponentBox] = field(default_factory=list)
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
class Deduction:
    code: str
    source: str
    severity: str
    score_delta: float
    reason: str
    evidence: str = ""
    component_ids: list[str] = field(default_factory=list)
    fix_hint: str = ""
    prompt_hint: str = ""
    # 问题幅度（0..1，越大越糟），用于递进式硬封顶；None 表示未评估，封顶回退固定基础值。
    magnitude: float | None = None


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
    # 封顶前的原始加权总分（保留 2 位小数）；overall = min(raw_overall, final_min_cap)。
    raw_overall: float
    grade: str
    confidence: float
    dimensions: list[DimensionResult]
    metrics: list[MetricResult]
    required_texts: list[RequiredText]
    missing_texts: list[str]
    deductions: list[Deduction]
    prompt_suggestions: list[str]
    hard_caps: list[dict[str, Any]]
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
