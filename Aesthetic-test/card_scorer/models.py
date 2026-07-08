"""Core data models for the Card Aesthetic Scoring System.

All modules share these types for input/output contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Basic geometry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BBox:
    """Axis-aligned bounding box (pixel coordinates)."""
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    def iou(self, other: BBox) -> float:
        """Intersection over Union with another BBox."""
        ix1 = max(self.x1, other.x1)
        iy1 = max(self.y1, other.y1)
        ix2 = min(self.x2, other.x2)
        iy2 = min(self.y2, other.y2)
        inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
        union = self.area + other.area - inter
        if union <= 0:
            return 0.0
        return inter / union


# ---------------------------------------------------------------------------
# Extracted elements
# ---------------------------------------------------------------------------

@dataclass
class TextElement:
    """A text region detected by OCR."""
    text: str
    bbox: BBox
    confidence: float
    font_size_est: Optional[float] = None  # estimated from bbox height


@dataclass
class ComponentElement:
    """A non-text visual component detected by connected-component analysis."""
    bbox: BBox
    area: float
    centroid: tuple[float, float]
    label_id: int = 0  # connected-component label


@dataclass
class ColorInfo:
    """Dominant color extracted from the image."""
    rgb: tuple[int, int, int]
    hsv: tuple[float, float, float]
    proportion: float  # 0.0 ~ 1.0


# ---------------------------------------------------------------------------
# Rule results
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    """Rule severity levels."""
    FATAL = "fatal"    # triggers FAIL cap
    MAJOR = "major"
    MINOR = "minor"
    INFO = "info"


@dataclass
class RuleResult:
    """Output of a single rule evaluation.

    Every rule MUST produce this; boolean-only outputs are not allowed.
    """
    rule_id: str
    rule_name: str
    dimension: str
    passed: bool
    score_delta: float          # negative = deduction
    severity: Severity
    evidence: dict[str, Any]    # machine-readable detection evidence
    explanation: str            # human-readable, e.g. "Temperature text 4px from right edge (<16px threshold)"
    suggestion: str = ""        # repair suggestion


# ---------------------------------------------------------------------------
# Dimension summary
# ---------------------------------------------------------------------------

@dataclass
class DimensionScore:
    """Aggregated score for a single scoring dimension."""
    dimension: str
    dimension_name: str
    max_deduction: float
    actual_deduction: float
    rule_results: list[RuleResult] = field(default_factory=list)

    @property
    def score(self) -> float:
        """Remaining score for this dimension (>= 0)."""
        return max(0.0, self.max_deduction - self.actual_deduction)


# ---------------------------------------------------------------------------
# Final scoring report
# ---------------------------------------------------------------------------

@dataclass
class ScoringReport:
    """Complete scoring output for a single card."""
    total_score: float
    status: str                 # "PASS" or "FAIL"
    fail_triggered: bool
    dimensions: list[DimensionScore] = field(default_factory=list)
    all_results: list[RuleResult] = field(default_factory=list)
    deduction_details: list[RuleResult] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    # ✨ P0-2 修复：警告列表（如 DSL 解析失败）
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Scoring context (shared state across pipeline)
# ---------------------------------------------------------------------------

@dataclass
class ScoringContext:
    """Carries all extracted data through the pipeline.

    Built by extractors, consumed by analyzers and rules.
    """
    # Input
    query: str = ""
    image_path: str = ""
    dsl_path: str = ""
    image_width: int = 0
    image_height: int = 0

    # Extracted elements
    text_elements: list[TextElement] = field(default_factory=list)
    component_elements: list[ComponentElement] = field(default_factory=list)
    dominant_colors: list[ColorInfo] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    dsl_tree: Optional[dict[str, Any]] = None

    # ✨ P0-2 修复：DSL 加载状态
    dsl_status: str = "NOT_PROVIDED"  # "OK" | "NOT_PROVIDED" | "FILE_NOT_FOUND" | "PARSE_FAILED"

    # Intent analysis (populated by intent classifier)
    intent_result: Optional[dict[str, Any]] = None

    # Computed features (populated by analyzers)
    features: dict[str, Any] = field(default_factory=dict)
