from pathlib import Path

from aesthetic_rule_check.config import Config
from aesthetic_rule_check.metrics import MetricContext, create_metrics
from aesthetic_rule_check.metrics.consistency import (
    ComponentSizeMetric,
    CornerRadiusConsistencyMetric,
    IconSizeConsistencyMetric,
    PaddingConsistencyMetric,
)
from aesthetic_rule_check.metrics.information import DuplicateMetric, TruncationMetric
from aesthetic_rule_check.metrics.layout import SpacingRhythmMetric
from aesthetic_rule_check.metrics.visual import ContrastMetric, visual_weight
from aesthetic_rule_check.models import DslInfo, Rect, RequiredText, VisionContext, VisualElement


def make_context() -> MetricContext:
    vision = VisionContext(
        image_path=Path("missing.png"),
        width=100,
        height=100,
        card_bbox=Rect(0, 0, 100, 100),
        text_blocks=[],
        elements=[],
        dominant_colors=[(255, 255, 255)],
        color_proportions=[1.0],
        confidence=0.0,
    )
    dsl = DslInfo(
        path=None,
        required_texts=[RequiredText(text="天气", source="text.content")],
        data_model={},
        component_count=1,
    )
    return MetricContext(query="", dsl=dsl, vision=vision, config=Config())


def test_no_ocr_text_does_not_get_text_metric_passes() -> None:
    context = make_context()

    assert TruncationMetric().evaluate(context).score == 0.0
    assert DuplicateMetric().evaluate(context).score == 0.0
    assert ContrastMetric().evaluate(context).score == 0.0


def test_insufficient_visual_samples_are_skipped() -> None:
    context = make_context()

    spacing = SpacingRhythmMetric().evaluate(context)
    component_size = ComponentSizeMetric().evaluate(context)

    assert spacing.score is None
    assert spacing.status == "skipped"
    assert component_size.score is None
    assert component_size.status == "skipped"


def test_metric_modules_are_discovered_without_manual_import_list() -> None:
    keys = {(metric.dimension, metric.name) for metric in create_metrics()}

    assert ("information", "coverage") in keys
    assert ("layout", "whitespace") in keys
    assert ("visual", "contrast") in keys
    assert ("consistency", "alignment") in keys


def test_finish_metrics_use_visual_features() -> None:
    context = make_context()
    vision = VisionContext(
        image_path=Path("sample.png"),
        width=100,
        height=100,
        card_bbox=Rect(0, 0, 100, 100),
        text_blocks=[],
        elements=[
            VisualElement(kind="icon", bbox=Rect(5, 5, 10, 10), radius=4),
            VisualElement(kind="icon", bbox=Rect(20, 5, 10, 10), radius=4),
            VisualElement(kind="button", bbox=Rect(5, 30, 50, 18), radius=6, style_features={"padding": [8, 8, 4, 4]}),
            VisualElement(kind="tag", bbox=Rect(5, 55, 50, 18), radius=6, style_features={"padding": [8, 8, 4, 4]}),
        ],
        dominant_colors=[(255, 255, 255), (20, 20, 20)],
        color_proportions=[0.8, 0.2],
        confidence=1.0,
    )
    context = MetricContext(query=context.query, dsl=context.dsl, vision=vision, config=context.config)

    assert CornerRadiusConsistencyMetric().evaluate(context).status == "ok"
    assert PaddingConsistencyMetric().evaluate(context).status == "ok"
    assert IconSizeConsistencyMetric().evaluate(context).score == 100.0


def test_visual_weight_uses_text_contrast_and_font_size() -> None:
    context = make_context()
    small = VisualElement(
        kind="text",
        bbox=Rect(0, 0, 20, 10),
        style_features={"font_size": 10, "contrast_ratio": 2.0},
    )
    strong = VisualElement(
        kind="text",
        bbox=Rect(0, 0, 20, 10),
        style_features={"font_size": 24, "contrast_ratio": 8.0},
    )

    assert visual_weight(strong, context) > visual_weight(small, context)
