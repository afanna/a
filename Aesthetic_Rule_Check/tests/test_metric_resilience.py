from pathlib import Path

import cv2
import numpy as np

from aesthetic_rule_check.config import Config
from aesthetic_rule_check.deductions import collect_deductions, hard_caps_for
from aesthetic_rule_check.metrics import MetricContext, create_metrics
from aesthetic_rule_check.metrics.consistency import (
    ComponentSizeMetric,
    CornerRadiusConsistencyMetric,
    IconSizeConsistencyMetric,
    PaddingConsistencyMetric,
)
from aesthetic_rule_check.metrics.information import DuplicateMetric, TruncationMetric
from aesthetic_rule_check.metrics.layout import OverlapMetric, SpacingRhythmMetric, occupied_mask_ratio
from aesthetic_rule_check.metrics.visual import ContrastMetric, SparseTextStackMetric, visual_weight
from aesthetic_rule_check.models import DslInfo, Rect, RequiredText, TextBlock, VisionContext, VisualElement


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


def test_sparse_text_stack_penalizes_only_sparse_text_dominant_cards() -> None:
    context = make_context()
    sparse_blocks = [
        TextBlock("title", Rect(10, 10, 80, 8), 1.0, 8),
        TextBlock("body", Rect(10, 35, 80, 8), 1.0, 8),
    ]
    sparse_vision = VisionContext(
        image_path=Path("sample.png"),
        width=100,
        height=100,
        card_bbox=Rect(0, 0, 100, 100),
        text_blocks=sparse_blocks,
        elements=[VisualElement(kind="text", bbox=block.bbox) for block in sparse_blocks],
        dominant_colors=[(255, 255, 255)],
        color_proportions=[1.0],
        confidence=1.0,
    )
    dense_block = TextBlock("content", Rect(5, 5, 90, 80), 1.0, 80)
    dense_vision = VisionContext(
        image_path=Path("sample.png"),
        width=100,
        height=100,
        card_bbox=Rect(0, 0, 100, 100),
        text_blocks=[dense_block],
        elements=[VisualElement(kind="text", bbox=dense_block.bbox)],
        dominant_colors=[(255, 255, 255)],
        color_proportions=[1.0],
        confidence=1.0,
    )

    sparse_context = MetricContext(context.query, context.dsl, sparse_vision, context.config)
    dense_context = MetricContext(context.query, context.dsl, dense_vision, context.config)

    assert SparseTextStackMetric().evaluate(sparse_context).score < 20
    dense_result = SparseTextStackMetric().evaluate(dense_context)
    assert dense_result.score is None
    assert dense_result.status == "not_applicable"


def test_sparse_text_stack_uses_pixel_foreground_when_graphics_are_missed(tmp_path: Path) -> None:
    image_path = tmp_path / "graphic_card.png"
    image = np.full((100, 100, 3), 255, dtype=np.uint8)
    image[10:90, 10:90] = (32, 80, 180)
    assert cv2.imwrite(str(image_path), image)

    context = make_context()
    blocks = [
        TextBlock("6", Rect(35, 30, 20, 18), 1.0, 18),
        TextBlock("hours", Rect(35, 55, 35, 10), 1.0, 10),
    ]
    vision = VisionContext(
        image_path=image_path,
        width=100,
        height=100,
        card_bbox=Rect(0, 0, 100, 100),
        text_blocks=blocks,
        elements=[VisualElement(kind="text", bbox=block.bbox) for block in blocks],
        dominant_colors=[(255, 255, 255), (180, 80, 32)],
        color_proportions=[0.36, 0.64],
        confidence=1.0,
    )
    context = MetricContext(context.query, context.dsl, vision, context.config)

    result = SparseTextStackMetric().evaluate(context)

    assert result.score is None
    assert result.status == "not_applicable"
    assert result.value["pixel_foreground_density"] > result.value["element_density"]


def test_layout_occupancy_uses_pixel_foreground_when_elements_miss_large_shapes(tmp_path: Path) -> None:
    image_path = tmp_path / "foreground.png"
    image = np.full((100, 100, 3), 255, dtype=np.uint8)
    image[10:90, 10:90] = (32, 160, 64)
    assert cv2.imwrite(str(image_path), image)

    context = make_context()
    vision = VisionContext(
        image_path=image_path,
        width=100,
        height=100,
        card_bbox=Rect(0, 0, 100, 100),
        text_blocks=[],
        elements=[VisualElement(kind="icon", bbox=Rect(45, 45, 10, 10))],
        dominant_colors=[(255, 255, 255), (64, 160, 32)],
        color_proportions=[0.36, 0.64],
        confidence=1.0,
    )
    context = MetricContext(query=context.query, dsl=context.dsl, vision=vision, config=context.config)

    ratio = occupied_mask_ratio(context, {"pixel_foreground_lab_threshold": 35})

    assert ratio > 0.6


def test_layout_overlap_deduction_triggers_above_generic_score_gate() -> None:
    context = make_context()
    vision = VisionContext(
        image_path=Path("sample.png"),
        width=100,
        height=100,
        card_bbox=Rect(0, 0, 100, 100),
        text_blocks=[],
        elements=[
            VisualElement(kind="text", bbox=Rect(10, 10, 50, 20)),
            VisualElement(kind="button", bbox=Rect(49, 10, 50, 20)),
        ],
        dominant_colors=[(255, 255, 255)],
        color_proportions=[1.0],
        confidence=1.0,
    )
    context = MetricContext(context.query, context.dsl, vision, context.config)

    result = OverlapMetric().evaluate(context)
    deductions = collect_deductions([result])
    caps = hard_caps_for(deductions)

    assert result.score is not None and result.score > 65
    assert result.details["deductions"]
    assert deductions[0].code == "layout.overlap"
    assert caps and caps[0]["code"] == "layout.overlap"
