#!/usr/bin/env python3
"""Conservative DSL-only aesthetic checks for HarmonyOS A2UI Form cards.

Default scope: three visible-evidence risks only: overlap, text crowding, and text/control edge contact.
Contrast and subjective proxy rules are opt-in.
Precondition: the DSL has already passed the existing hard/protocol validator.
No renderer, screenshot, OCR, network call, model, or third-party dependency is used.
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeAlias


RGBA: TypeAlias = tuple[float, float, float, float]
MAX_BACKGROUND_CANDIDATES = 4096
MIN_PROVABLE_FIXED_OVERFLOW_VP = 4.0
MIN_PROVABLE_ROOT_COLUMN_OVERFLOW_VP = 8.0
MIN_PROVABLE_TEXT_CLIP_RATIO = 1.3
MIN_PROVABLE_TEXT_DENSITY_RATIO = 1.2
MIN_PROVABLE_NON_SURFACE_TEXT_STACK_OVERFLOW_VP = 4.0
CHECKBOX_INTRINSIC_SIZE_VP = 20.0
ROUNDED_SURFACE_PAIR_GAP_VP = 0.5
ROOT_ACTION_CONTENT_FILL_EPSILON_VP = 0.5
ESTIMATED_TEXT_LINE_HEIGHT_RATIO = 1.25
ESTIMATED_TEXT_SURFACE_GAP_VP = 2.0


@dataclass(frozen=True)
class Thresholds:
    normal_text_min: float = 4.5
    large_text_min: float = 3.0
    critical_min: float = 3.0
    large_font_size: float = 18.0
    large_bold_font_size: float = 14.0
    large_bold_font_weight: float = 700.0
    max_chromatic_families: int = 2
    max_gradient_surfaces: int = 1
    max_gradient_stops: int = 3
    max_translucent_surface_layers: int = 2
    max_font_size_levels: int = 3
    max_radius_values: int = 3
    max_shadowed_components: int = 2
    max_border_width_values: int = 2
    max_nested_surfaces: int = 2

    def __post_init__(self) -> None:
        values = {
            "normal_text_min": self.normal_text_min,
            "large_text_min": self.large_text_min,
            "critical_min": self.critical_min,
            "large_font_size": self.large_font_size,
            "large_bold_font_size": self.large_bold_font_size,
            "large_bold_font_weight": self.large_bold_font_weight,
            "max_chromatic_families": self.max_chromatic_families,
            "max_gradient_surfaces": self.max_gradient_surfaces,
            "max_gradient_stops": self.max_gradient_stops,
            "max_translucent_surface_layers": self.max_translucent_surface_layers,
            "max_font_size_levels": self.max_font_size_levels,
            "max_radius_values": self.max_radius_values,
            "max_shadowed_components": self.max_shadowed_components,
            "max_border_width_values": self.max_border_width_values,
            "max_nested_surfaces": self.max_nested_surfaces,
        }
        for name, value in values.items():
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
            ):
                raise ValueError(f"{name} 必须是有限数值")

        if not (
            1.0
            <= self.critical_min
            <= self.large_text_min
            <= self.normal_text_min
            <= 21.0
        ):
            raise ValueError(
                "对比度阈值必须满足 "
                "1 <= critical_min <= large_text_min <= normal_text_min <= 21"
            )
        if not (
            0.0 < self.large_bold_font_size <= self.large_font_size
        ):
            raise ValueError(
                "字号阈值必须满足 0 < large_bold_font_size <= large_font_size"
            )
        if not 100.0 <= self.large_bold_font_weight <= 900.0:
            raise ValueError("large_bold_font_weight 必须位于 100 到 900")
        if not 1 <= self.max_chromatic_families <= 8:
            raise ValueError("max_chromatic_families 必须位于 1 到 8")
        if not 1 <= self.max_gradient_surfaces <= 4:
            raise ValueError("max_gradient_surfaces 必须位于 1 到 4")
        if not 2 <= self.max_gradient_stops <= 8:
            raise ValueError("max_gradient_stops 必须位于 2 到 8")
        if not 1 <= self.max_translucent_surface_layers <= 6:
            raise ValueError("max_translucent_surface_layers 必须位于 1 到 6")
        if not 2 <= self.max_font_size_levels <= 8:
            raise ValueError("max_font_size_levels 必须位于 2 到 8")
        if not 1 <= self.max_radius_values <= 6:
            raise ValueError("max_radius_values 必须位于 1 到 6")
        if not 0 <= self.max_shadowed_components <= 6:
            raise ValueError("max_shadowed_components 必须位于 0 到 6")
        if not 1 <= self.max_border_width_values <= 4:
            raise ValueError("max_border_width_values 必须位于 1 到 4")
        if not 1 <= self.max_nested_surfaces <= 5:
            raise ValueError("max_nested_surfaces 必须位于 1 到 5")


@dataclass(frozen=True)
class AestheticContext:
    components: list[dict[str, Any]]
    components_by_id: dict[str, dict[str, Any]]
    source_index_by_id: dict[str, int]
    parent_by_child: dict[str, str]
    data_model: dict[str, Any]
    root_id: str
    surface_width: float | None
    surface_height: float | None


@dataclass(frozen=True)
class StaticLayoutEstimate:
    rect_by_id: dict[str, tuple[float, float, float, float]]
    dimension_source_by_id: dict[str, tuple[str, str]]
    unresolved_reasons: list[str]


def read_text(path: str) -> str:
    if path == "-":
        return sys.stdin.read().lstrip("\ufeff")
    return Path(path).read_text(encoding="utf-8-sig")


def extract_genui(raw: str) -> str:
    match = re.search(r"```genui\s*([\s\S]*?)```", raw, re.I)
    return match.group(1).strip() if match else raw.strip()


def reject_nonfinite_json_constant(constant: str) -> Any:
    raise ValueError(f"不允许非有限数值 {constant}")


def prepare_context(raw: str) -> tuple[AestheticContext | None, list[dict[str, Any]]]:
    """Build the graph needed by the aesthetic algorithm.

    This is a defensive precondition assertion, not a replacement for validate_card.py.
    It only blocks graph ambiguity that would make a contrast result untrustworthy.
    """

    reasons: list[str] = []
    messages: list[dict[str, Any]] = []
    payload = extract_genui(raw)
    try:
        document = json.loads(payload, parse_constant=reject_nonfinite_json_constant)
    except (json.JSONDecodeError, ValueError):
        document = None

    if isinstance(document, list):
        for item_index, value in enumerate(document):
            if not isinstance(value, dict):
                reasons.append(f"JSON 数组第 {item_index} 项不是 object")
                continue
            messages.append(value)
    elif isinstance(document, dict):
        messages.append(document)
    else:
        for line_number, line in enumerate(
            [line.strip() for line in payload.splitlines() if line.strip()], 1
        ):
            try:
                value = json.loads(line, parse_constant=reject_nonfinite_json_constant)
            except (json.JSONDecodeError, ValueError) as exc:
                detail = exc.msg if isinstance(exc, json.JSONDecodeError) else str(exc)
                reasons.append(f"第 {line_number} 行 JSON 无法解析：{detail}")
                continue
            if not isinstance(value, dict):
                reasons.append(f"第 {line_number} 行不是 JSON object")
                continue
            messages.append(value)

    updates = [
        message["updateComponents"]
        for message in messages
        if isinstance(message.get("updateComponents"), dict)
    ]
    if len(updates) != 1:
        reasons.append(f"需要 1 个 updateComponents，实际为 {len(updates)} 个")
        return None, [precondition_diagnostic(reasons)]

    update = updates[0]
    raw_components = update.get("components")
    if not isinstance(raw_components, list) or not raw_components:
        reasons.append("updateComponents.components 必须是非空数组")
        return None, [precondition_diagnostic(reasons)]
    if any(not isinstance(item, dict) for item in raw_components):
        reasons.append("components 数组包含非 object 项")
        return None, [precondition_diagnostic(reasons)]
    components = list(raw_components)

    components_by_id: dict[str, dict[str, Any]] = {}
    source_index_by_id: dict[str, int] = {}
    duplicate_ids: set[str] = set()
    for index, component in enumerate(components):
        component_id = component.get("id")
        if not isinstance(component_id, str) or not component_id:
            reasons.append(f"components[{index}].id 不是非空字符串")
            continue
        if component_id in components_by_id:
            duplicate_ids.add(component_id)
            continue
        components_by_id[component_id] = component
        source_index_by_id[component_id] = index
        if (
            component.get("component") in {"Text", "Button"}
            and has_visible_text(component)
            and not isinstance(component.get("styles"), dict)
        ):
            reasons.append(f"可见文字组件 {component_id} 缺少 object styles")
    if duplicate_ids:
        reasons.append("组件 id 重复：" + ", ".join(sorted(duplicate_ids)))

    root_id = update.get("root")
    if not isinstance(root_id, str) or root_id not in components_by_id:
        reasons.append("updateComponents.root 未指向已声明组件")

    parents_by_child: dict[str, set[str]] = {}
    children_by_parent: dict[str, list[str]] = {}
    for component in components:
        parent_id = component.get("id")
        if not isinstance(parent_id, str) or parent_id not in components_by_id:
            continue
        children = component.get("children")
        if children is None:
            children_by_parent[parent_id] = []
            continue
        if isinstance(children, list):
            child_ids = [item for item in children if isinstance(item, str)]
            if len(child_ids) != len(children):
                reasons.append(f"{parent_id}.children 含非字符串引用")
        elif isinstance(children, dict) and isinstance(children.get("componentId"), str):
            child_ids = [children["componentId"]]
        else:
            reasons.append(f"{parent_id}.children 无法解析")
            child_ids = []
        if len(child_ids) != len(set(child_ids)):
            reasons.append(f"{parent_id}.children 重复引用同一组件")
        children_by_parent[parent_id] = child_ids
        for child_id in child_ids:
            if child_id not in components_by_id:
                reasons.append(f"{parent_id}.children 引用了不存在的 {child_id}")
                continue
            parents_by_child.setdefault(child_id, set()).add(parent_id)

    ambiguous_children = {
        child_id: sorted(parent_ids)
        for child_id, parent_ids in parents_by_child.items()
        if len(parent_ids) > 1
    }
    if ambiguous_children:
        reasons.append(
            "组件存在多个父节点："
            + "; ".join(
                f"{child_id}<-{','.join(parent_ids)}"
                for child_id, parent_ids in sorted(ambiguous_children.items())
            )
        )
    parent_by_child = {
        child_id: next(iter(parent_ids))
        for child_id, parent_ids in parents_by_child.items()
        if len(parent_ids) == 1
    }
    if has_parent_cycle(parent_by_child, set(components_by_id)):
        reasons.append("组件父子关系存在循环")

    if isinstance(root_id, str) and root_id in components_by_id:
        reachable: set[str] = set()
        pending = [root_id]
        while pending:
            current_id = pending.pop()
            if current_id in reachable:
                continue
            reachable.add(current_id)
            pending.extend(children_by_parent.get(current_id, []))
        unreachable = sorted(set(components_by_id) - reachable)
        if unreachable:
            reasons.append("存在 root 不可达组件：" + ", ".join(unreachable))

    if reasons:
        return None, [precondition_diagnostic(reasons)]
    create_surface = next(
        (
            message.get("createSurface")
            for message in messages
            if isinstance(message.get("createSurface"), dict)
        ),
        {},
    )
    data_model: dict[str, Any] = {}
    for message in messages:
        update_data = message.get("updateDataModel")
        if not isinstance(update_data, dict):
            continue
        apply_data_model_update(
            data_model,
            update_data.get("path"),
            update_data.get("value"),
        )
    return (
        AestheticContext(
            components=components,
            components_by_id=components_by_id,
            source_index_by_id=source_index_by_id,
            parent_by_child=parent_by_child,
            data_model=data_model,
            root_id=root_id,
            surface_width=numeric(create_surface.get("width")),
            surface_height=numeric(create_surface.get("height")),
        ),
        [],
    )


def apply_data_model_update(model: dict[str, Any], path: object, value: object) -> None:
    if path in (None, "", "/"):
        if isinstance(value, dict):
            model.update(value)
        return
    if not isinstance(path, str) or not path.startswith("/"):
        return
    tokens = [token for token in path.split("/")[1:] if token]
    if not tokens:
        return
    current = model
    for token in tokens[:-1]:
        child = current.get(token)
        if not isinstance(child, dict):
            child = {}
            current[token] = child
        current = child
    current[tokens[-1]] = value


def precondition_diagnostic(reasons: list[str]) -> dict[str, Any]:
    return diagnostic(
        "error",
        "AESTHETIC_PRECONDITION_FAILED",
        "输入不满足美学算法的前置条件；请先通过现有 hard/协议校验器。",
        json_pointer="/updateComponents",
        actual={"reasons": reasons[:20]},
        expected="validate_card.py hard stage passed",
        fix_hint="先修复或合并 DSL 结构错误，再运行美学算法；本脚本不替代协议校验器。",
    )


def has_parent_cycle(parent_by_child: dict[str, str], component_ids: set[str]) -> bool:
    for start_id in component_ids:
        visited: set[str] = set()
        current_id: str | None = start_id
        while current_id is not None:
            if current_id in visited:
                return True
            visited.add(current_id)
            current_id = parent_by_child.get(current_id)
    return False


def analyze(
    raw: str,
    thresholds: Thresholds | None = None,
    *,
    include_contrast: bool = False,
    include_heuristics: bool = False,
) -> dict[str, Any]:
    thresholds = thresholds or Thresholds()
    context, diagnostics = prepare_context(raw)
    if context is None:
        report = build_report([], 0, 0, diagnostics, thresholds)
        attach_rule_assessments(report, [])
        report["analysisProfile"] = analysis_profile(
            include_contrast, include_heuristics
        )
        return report

    text_like_count = 0
    checked_count = 0
    for component in context.components:
        component_type = component.get("component")
        if component_type not in {"Text", "Button"} or not has_visible_text(component):
            continue
        component_id = component.get("id")
        styles = component.get("styles")
        if not isinstance(component_id, str) or not isinstance(styles, dict):
            continue
        if not is_effectively_visible(
            component_id, context.components_by_id, context.parent_by_child
        ):
            continue
        text_like_count += 1
        if not include_contrast:
            continue
        source_index = context.source_index_by_id[component_id]
        pointer = f"/updateComponents/components/{source_index}/styles/fontColor"
        logical_path = (
            f"/updateComponents/componentsById/{component_id}/styles/fontColor"
        )
        foreground_value = styles.get("fontColor")
        foreground = parse_hex_color(foreground_value)
        if foreground is None:
            diagnostics.append(
                diagnostic(
                    "warning",
                    "AESTHETIC_COLOR_CONTRAST_UNDETERMINED",
                    "文字颜色不是可静态解析的 hex，无法确定对比度。",
                    json_pointer=pointer,
                    logical_path=logical_path,
                    actual={"componentId": component_id, "fontColor": foreground_value},
                    expected="#RRGGBB 或 #AARRGGBB",
                    fix_hint="提供静态 fontColor，或在真实渲染后由 UCD 复核。",
                )
            )
            continue

        backgrounds, background_layers, uncertainty = resolve_background_candidates(
            component_id,
            context.components_by_id,
            context.parent_by_child,
        )
        ratios = [
            ratio
            for background in backgrounds
            if (ratio := contrast_ratio(foreground, background)) is not None
        ]
        if not ratios:
            diagnostics.append(
                diagnostic(
                    "warning",
                    "AESTHETIC_COLOR_CONTRAST_UNDETERMINED",
                    "背景包含图片、动态颜色或无法闭合的透明叠层，无法从 DSL 确定对比度。",
                    json_pointer=pointer,
                    logical_path=logical_path,
                    actual={
                        "componentId": component_id,
                        "fontColor": foreground_value,
                        "backgroundLayers": background_layers,
                        "uncertainty": uncertainty,
                    },
                    fix_hint="该组件不能被自动判定为通过；请在真实渲染后由 UCD 复核。",
                )
            )
            continue

        raw_font_size = styles.get("fontSize")
        font_size = numeric(raw_font_size)
        if font_size is None and "fontSize" in styles:
            diagnostics.append(
                diagnostic(
                    "warning",
                    "AESTHETIC_COLOR_CONTRAST_UNDETERMINED",
                    "字号是动态或不可静态解析的值，无法选择文字对比度阈值。",
                    json_pointer=f"/updateComponents/components/{source_index}/styles/fontSize",
                    logical_path=f"/updateComponents/componentsById/{component_id}/styles/fontSize",
                    actual={"componentId": component_id, "fontSize": raw_font_size},
                    expected="静态 fontSize，或真实渲染后的可读性复核。",
                    fix_hint="提供静态字号，或将此组件纳入真实渲染与 UCD 可读性复核。",
                )
            )
            continue
        if font_size is None:
            font_size = 16.0
        checked_count += 1
        classification_font_size, adaptive_font_size_uncertain = (
            smallest_possible_font_size(styles, font_size)
        )
        raw_font_weight = styles.get("fontWeight")
        font_weight = normalize_font_weight(raw_font_weight, component_type)
        is_large = classification_font_size >= thresholds.large_font_size or (
            classification_font_size >= thresholds.large_bold_font_size
            and font_weight >= thresholds.large_bold_font_weight
        )
        required = thresholds.large_text_min if is_large else thresholds.normal_text_min
        ratio = min(ratios)
        best_ratio = max(ratios)
        if ratio >= required:
            continue
        if best_ratio >= required:
            diagnostics.append(
                diagnostic(
                    "warning",
                    "AESTHETIC_COLOR_CONTRAST_UNDETERMINED",
                    "文字所在位置的实际背景无法由 DSL 唯一确定，不能据此判定对比度不足。",
                    json_pointer=pointer,
                    logical_path=logical_path,
                    actual={
                        "componentId": component_id,
                        "componentType": component_type,
                        "fontColor": foreground_value,
                        "backgroundLayers": background_layers,
                        "contrastRatioRange": [round(ratio, 2), round(best_ratio, 2)],
                        "fontSize": raw_font_size,
                        "normalizedFontSize": font_size,
                        "fontWeight": raw_font_weight,
                    },
                    expected={"contrastRatio": f">= {required}:1"},
                    fix_hint="结合真实渲染确认文字所在区域的实际背景后再判断，不自动判错。",
                )
            )
            continue
        severity = "error" if ratio < thresholds.critical_min else "warning"
        diagnostics.append(
            diagnostic(
                severity,
                "AESTHETIC_COLOR_CONTRAST_LOW",
                "文字与背景的对比度不足，可能看不清楚。",
                json_pointer=pointer,
                logical_path=logical_path,
                actual={
                    "componentId": component_id,
                    "componentType": component_type,
                    "fontColor": foreground_value,
                    "backgroundLayers": background_layers,
                    "contrastRatio": round(ratio, 2),
                    "fontSize": raw_font_size,
                    "normalizedFontSize": font_size,
                    "classificationFontSize": classification_font_size,
                    "minFontSize": styles.get("minFontSize"),
                    "maxFontSize": styles.get("maxFontSize"),
                    "adaptiveFontSizeUncertain": adaptive_font_size_uncertain,
                    "fontWeight": raw_font_weight,
                    "normalizedFontWeight": font_weight,
                    "largeText": is_large,
                },
                expected={"contrastRatio": f">= {required}:1"},
                fix_hint="提高文字与背景的明暗差，或改用高对比的文字/背景色。",
            )
        )

    fixed_overflow_diagnostics = evaluate_fixed_layout_overflow(context)
    diagnostics.extend(fixed_overflow_diagnostics)
    fixed_overflow_ids = {
        item.get("actual", {}).get("containerId")
        for item in fixed_overflow_diagnostics
        if isinstance(item.get("actual"), dict)
    }
    diagnostics.extend(
        evaluate_vertical_text_stack_density(context, fixed_overflow_ids)
    )
    diagnostics.extend(evaluate_adjacent_text_clearance(context))
    diagnostics.extend(evaluate_adjacent_control_clearance(context))
    diagnostics.extend(evaluate_intrinsic_control_clearance(context))
    text_icon_diagnostics = evaluate_text_icon_clearance(context)
    diagnostics.extend(text_icon_diagnostics)
    surface_content_diagnostics = evaluate_surface_content_edge_clearance(context)
    diagnostics.extend(surface_content_diagnostics)
    diagnostics.extend(evaluate_action_surface_edge_clearance(context))
    stack_overlap_diagnostics = evaluate_stack_text_image_overlap(context)
    diagnostics.extend(stack_overlap_diagnostics)
    diagnostics.extend(evaluate_static_text_clip_risk(context))
    fragment_diagnostics = evaluate_inline_text_fragment_risk(context)
    diagnostics.extend(fragment_diagnostics)
    diagnostics.extend(evaluate_static_pill_content_bounds(context))
    if include_heuristics:
        diagnostics.extend(evaluate_rounded_surface_root_edge_safety(context))
        diagnostics.extend(evaluate_rounded_surface_pair_gap(context))
        diagnostics.extend(evaluate_estimated_text_surface_overlap(context))
        diagnostics.extend(evaluate_repeated_group_spacing(context))
        diagnostics.extend(evaluate_action_target_size(context))
        diagnostics.extend(evaluate_palette_complexity(context, thresholds))
        diagnostics.extend(evaluate_color_role_consistency(context))
        diagnostics.extend(evaluate_gradient_complexity(context, thresholds))
        diagnostics.extend(evaluate_alpha_stack_complexity(context, thresholds))
        diagnostics.extend(evaluate_typography_system(context, thresholds))
        diagnostics.extend(evaluate_style_consistency(context, thresholds))
        diagnostics.extend(evaluate_surface_nesting(context, thresholds))
        diagnostics.extend(evaluate_spacing_tokens(context))
        diagnostics.extend(evaluate_false_affordance(context))
        diagnostics.extend(evaluate_information_hierarchy(context))
        diagnostics.extend(evaluate_small_card_density(context))

    report = build_report(
        context.components,
        text_like_count,
        checked_count,
        diagnostics,
        thresholds,
    )
    report["analysisProfile"] = analysis_profile(
        include_contrast, include_heuristics
    )
    attach_rule_assessments(
        report,
        [
            assess_checkbox_text_clearance(context, text_icon_diagnostics),
            assess_runtime_spacing_contract(context),
            assess_rounded_surface_content_clearance(
                context, surface_content_diagnostics
            ),
            assess_stack_text_image_overlap(context, stack_overlap_diagnostics),
            assess_inline_cjk_fragment_clip(context, fragment_diagnostics),
        ],
    )
    return report


def analysis_profile(include_contrast: bool, include_heuristics: bool) -> str:
    additions = []
    if include_contrast:
        additions.append("contrast")
    if include_heuristics:
        additions.append("heuristics")
    return "three_visible_evidence" + (
        "_with_" + "_and_".join(additions) if additions else ""
    )


COLOR_STYLE_FIELDS = (
    "backgroundColor",
    "fontColor",
    "borderColor",
    "color",
    "selectedColor",
    "unSelectedColor",
)


def evaluate_palette_complexity(
    context: AestheticContext, thresholds: Thresholds
) -> list[dict[str, Any]]:
    """Detect competing chromatic families from DSL-defined, visible colors only.

    Image pixels and dynamic expressions are intentionally excluded: they cannot be
    analysed without a renderer or multimodal model.
    """

    families: dict[int, set[str]] = {}
    hues: list[float] = []
    for component in context.components:
        component_id = component.get("id")
        if not isinstance(component_id, str) or not is_effectively_visible(
            component_id, context.components_by_id, context.parent_by_child
        ):
            continue
        styles = component.get("styles")
        if not isinstance(styles, dict):
            continue
        for color in iter_static_style_colors(styles):
            hue = chromatic_hue_degrees(color)
            if hue is None:
                continue
            hues.append(hue)
            family = int(hue // 30) % 12
            families.setdefault(family, set()).add(component_id)

    hue_span = minimum_circular_hue_span(hues)
    if (
        len(families) <= thresholds.max_chromatic_families
        or hue_span <= 65.0
    ):
        return []
    return [
        diagnostic(
            "warning",
            "AESTHETIC_COLOR_PALETTE_TOO_COMPLEX",
            "同一卡片出现过多无关高饱和色族，视觉焦点可能相互竞争。",
            json_pointer="/updateComponents/components",
            actual={
                "chromaticFamilyCount": len(families),
                "hueFamilies": sorted(families),
                "minimumHueSpanDegrees": round(hue_span, 1),
                "componentIds": sorted(
                    {component_id for values in families.values() for component_id in values}
                ),
            },
            expected={"maxChromaticFamilies": thresholds.max_chromatic_families},
            fix_hint="保留一个场景主色与一个状态/动作色，其余颜色改为中性或同色族辅助色。",
        )
    ]


def evaluate_gradient_complexity(
    context: AestheticContext, thresholds: Thresholds
) -> list[dict[str, Any]]:
    gradients: list[tuple[str, int]] = []
    for component in context.components:
        component_id = component.get("id")
        if not isinstance(component_id, str) or not is_effectively_visible(
            component_id, context.components_by_id, context.parent_by_child
        ):
            continue
        styles = component.get("styles")
        gradient = styles.get("linearGradient") if isinstance(styles, dict) else None
        colors = gradient.get("colors") if isinstance(gradient, dict) else None
        if isinstance(colors, list):
            gradients.append((component_id, len(colors)))

    largest_stop_count = max((stop_count for _, stop_count in gradients), default=0)
    if (
        len(gradients) <= thresholds.max_gradient_surfaces
        and largest_stop_count <= thresholds.max_gradient_stops
    ):
        return []
    return [
        diagnostic(
            "warning",
            "AESTHETIC_COLOR_GRADIENT_OVERCOMPLEX",
            "渐变面或渐变 stop 过多，卡片容易显得杂乱并削弱信息层级。",
            json_pointer="/updateComponents/components",
            actual={
                "gradientSurfaces": [component_id for component_id, _ in gradients],
                "stopCounts": {component_id: count for component_id, count in gradients},
            },
            expected={
                "maxGradientSurfaces": thresholds.max_gradient_surfaces,
                "maxGradientStops": thresholds.max_gradient_stops,
            },
            fix_hint="2×2 卡片优先保留一个渐变面，且使用 2–3 个有明确场景角色的 stop。",
        )
    ]


def evaluate_color_role_consistency(context: AestheticContext) -> list[dict[str, Any]]:
    """Check two low-cost color-role risks without treating UCD tokens as closed.

    Brand/scenario colors can legitimately extend the token system, therefore this
    algorithm does not reject unknown hex values. It only reports clearly competing
    accent surfaces and mutually inconsistent CTA colors inside the same card.
    """

    accent_surfaces: list[tuple[str, int]] = []
    action_families: dict[int, list[str]] = {}
    for component in context.components:
        component_id = component.get("id")
        styles = component.get("styles")
        if (
            not isinstance(component_id, str)
            or not isinstance(styles, dict)
            or not is_effectively_visible(
                component_id, context.components_by_id, context.parent_by_child
            )
        ):
            continue
        background = parse_hex_color(styles.get("backgroundColor"))
        family = chromatic_hue_family(background) if background is not None else None
        if family is not None and component_id in context.parent_by_child:
            accent_surfaces.append((component_id, family))
        if is_action_container(component) and family is not None:
            action_families.setdefault(family, []).append(component_id)

    diagnostics: list[dict[str, Any]] = []
    if len(accent_surfaces) > 3:
        diagnostics.append(
            diagnostic(
                "warning",
                "AESTHETIC_COLOR_ACCENT_OVERUSED",
                "同一卡片使用过多高饱和强调面，容易让每个元素都在争夺注意力。",
                json_pointer="/updateComponents/components",
                actual={"accentSurfaces": [{"componentId": item_id, "hueFamily": family} for item_id, family in accent_surfaces]},
                expected="紧凑卡片通常保留 1 个场景强调面，必要时再增加 1 个状态/动作强调面。",
                fix_hint="将次要面改为中性色或主色低饱和变体，避免每个标签都使用强色底。",
            )
        )
    if sum(len(component_ids) for component_ids in action_families.values()) >= 3 and len(action_families) >= 3:
        diagnostics.append(
            diagnostic(
                "warning",
                "AESTHETIC_COLOR_ROLE_INCONSISTENT",
                "同一卡片的多个 CTA 使用互不相关的强调色，动作角色缺少一致性。",
                json_pointer="/updateComponents/components",
                actual={"actionHueFamilies": {str(family): component_ids for family, component_ids in sorted(action_families.items())}},
                expected="同类 CTA 应复用同一动作色；不同颜色只用于明确的成功/警告/危险语义。",
                fix_hint="统一 CTA 色角色，保留语义状态色仅用于对应状态，而非随机区分按钮。",
            )
        )
    return diagnostics


def evaluate_alpha_stack_complexity(
    context: AestheticContext, thresholds: Thresholds
) -> list[dict[str, Any]]:
    deepest: tuple[str, list[str]] | None = None
    for component in context.components:
        component_id = component.get("id")
        if not isinstance(component_id, str) or not is_effectively_visible(
            component_id, context.components_by_id, context.parent_by_child
        ):
            continue
        translucent_ids: list[str] = []
        current_id: str | None = component_id
        while current_id is not None:
            current = context.components_by_id.get(current_id, {})
            styles = current.get("styles") if isinstance(current, dict) else None
            if isinstance(styles, dict) and has_translucent_surface(styles):
                translucent_ids.append(current_id)
            current_id = context.parent_by_child.get(current_id)
        if deepest is None or len(translucent_ids) > len(deepest[1]):
            deepest = (component_id, translucent_ids)

    if deepest is None or len(deepest[1]) <= thresholds.max_translucent_surface_layers:
        return []
    component_id, layer_ids = deepest
    return [
        diagnostic(
            "warning",
            "AESTHETIC_COLOR_ALPHA_STACK_COMPLEX",
            "同一视觉路径叠加过多半透明表面，颜色可能发灰或浑浊。",
            json_pointer=f"/updateComponents/components/{context.source_index_by_id[component_id]}",
            actual={"componentId": component_id, "translucentSurfaceIds": layer_ids},
            expected={"maxTranslucentSurfaceLayers": thresholds.max_translucent_surface_layers},
            fix_hint="合并相邻半透明背板，优先保留一层主表面和一层必要的弱分隔。",
        )
    ]


def has_translucent_surface(styles: dict[str, Any]) -> bool:
    background = parse_hex_color(styles.get("backgroundColor"))
    if background is not None and 0 < background[3] < 0.999:
        return True
    gradient = styles.get("linearGradient")
    if isinstance(gradient, dict) and isinstance(gradient.get("colors"), list):
        return any(
            (parsed := parse_hex_color(stop[0])) is not None and 0 < parsed[3] < 0.999
            for stop in gradient["colors"]
            if isinstance(stop, list) and stop
        )
    return False


def evaluate_typography_system(
    context: AestheticContext, thresholds: Thresholds
) -> list[dict[str, Any]]:
    font_sizes: dict[float, list[str]] = {}
    text_weights: list[tuple[str, float]] = []
    for component in context.components:
        component_id = component.get("id")
        component_type = component.get("component")
        styles = component.get("styles")
        if (
            component_type not in {"Text", "Button"}
            or not isinstance(component_id, str)
            or not isinstance(styles, dict)
            or not has_visible_text(component)
            or not is_effectively_visible(
                component_id, context.components_by_id, context.parent_by_child
            )
        ):
            continue
        raw_font_size = styles.get("fontSize")
        font_size = numeric(raw_font_size)
        if font_size is None and "fontSize" not in styles:
            font_size = 16.0
        if font_size is not None:
            font_sizes.setdefault(font_size, []).append(component_id)
        text_weights.append(
            (component_id, normalize_font_weight(styles.get("fontWeight"), component_type))
        )

    diagnostics: list[dict[str, Any]] = []
    if len(font_sizes) > thresholds.max_font_size_levels:
        diagnostics.append(
            diagnostic(
            "warning",
            "AESTHETIC_TYPO_TOO_MANY_LEVELS",
            "同一卡片使用过多字号层级，信息结构容易显得零散。",
            json_pointer="/updateComponents/components",
            actual={
                "fontSizeLevels": sorted(font_sizes),
                "componentIdsBySize": {
                    str(size): component_ids for size, component_ids in sorted(font_sizes.items())
                },
            },
            expected={"maxFontSizeLevels": thresholds.max_font_size_levels},
            fix_hint="2×2 卡片优先收敛为主信息、标题/状态、支撑信息三档字号。",
            )
        )
    if len(text_weights) >= 3 and all(weight >= 700 for _, weight in text_weights):
        diagnostics.append(
            diagnostic(
                "warning",
                "AESTHETIC_TYPO_BOLD_OVERUSED",
                "可见文字几乎全部使用粗体，主次关系会被压平。",
                json_pointer="/updateComponents/components",
                actual={"componentIds": [component_id for component_id, _ in text_weights]},
                expected="保留一个主信息或 CTA 使用粗体，其余文字使用 Regular/Medium。",
                fix_hint="降低标题、支撑信息或辅助标签的字重，只保留一个最强视觉焦点。",
            )
        )
    return diagnostics


def evaluate_style_consistency(
    context: AestheticContext, thresholds: Thresholds
) -> list[dict[str, Any]]:
    radii: dict[float, list[str]] = {}
    shadowed_component_ids: list[str] = []
    border_widths: dict[float, list[str]] = {}
    for component in context.components:
        component_id = component.get("id")
        if not isinstance(component_id, str) or not is_effectively_visible(
            component_id, context.components_by_id, context.parent_by_child
        ):
            continue
        styles = component.get("styles")
        if not isinstance(styles, dict):
            continue
        radius = numeric(styles.get("borderRadius"))
        if radius is not None and radius > 0:
            radii.setdefault(radius, []).append(component_id)

        shadow = styles.get("shadow")
        if shadow not in (None, "", False):
            shadowed_component_ids.append(component_id)

        border_width = numeric(styles.get("borderWidth"))
        if border_width is not None and border_width > 0:
            border_widths.setdefault(border_width, []).append(component_id)

    diagnostics: list[dict[str, Any]] = []
    if len(radii) > thresholds.max_radius_values:
        diagnostics.append(
            diagnostic(
            "warning",
            "AESTHETIC_STYLE_RADIUS_INCONSISTENT",
            "同一卡片使用过多圆角规格，组件体系缺少一致性。",
            json_pointer="/updateComponents/components",
            actual={
                "radiusValues": sorted(radii),
                "componentIdsByRadius": {
                    str(radius): component_ids for radius, component_ids in sorted(radii.items())
                },
            },
            expected={"maxRadiusValues": thresholds.max_radius_values},
            fix_hint="收敛为面板、小图标块和 pill 三类圆角角色，重复组件复用同一规格。",
            )
        )
    if len(shadowed_component_ids) > thresholds.max_shadowed_components:
        diagnostics.append(
            diagnostic(
                "warning",
                "AESTHETIC_STYLE_SHADOW_OVERUSED",
                "多个组件同时使用阴影，紧凑卡片容易产生视觉噪声。",
                json_pointer="/updateComponents/components",
                actual={"shadowedComponentIds": shadowed_component_ids},
                expected={"maxShadowedComponents": thresholds.max_shadowed_components},
                fix_hint="优先保留 root 或一个关键背板的低强度阴影，其余层用边框或色阶区分。",
            )
        )
    if len(border_widths) > thresholds.max_border_width_values:
        diagnostics.append(
            diagnostic(
                "warning",
                "AESTHETIC_STYLE_STROKE_INCONSISTENT",
                "同一卡片混用过多描边粗细，组件边界显得不统一。",
                json_pointer="/updateComponents/components",
                actual={
                    "borderWidthValues": sorted(border_widths),
                    "componentIdsByBorderWidth": {
                        str(width): component_ids
                        for width, component_ids in sorted(border_widths.items())
                    },
                },
                expected={"maxBorderWidthValues": thresholds.max_border_width_values},
                fix_hint="优先统一为一个主描边规格；只有进度、分隔线等独立角色才使用第二规格。",
            )
        )
    return diagnostics


def evaluate_surface_nesting(
    context: AestheticContext, thresholds: Thresholds
) -> list[dict[str, Any]]:
    deepest: tuple[str, list[str]] | None = None
    for component in context.components:
        component_id = component.get("id")
        if not isinstance(component_id, str) or not is_effectively_visible(
            component_id, context.components_by_id, context.parent_by_child
        ):
            continue
        surface_ids: list[str] = []
        current_id: str | None = component_id
        while current_id is not None:
            current = context.components_by_id.get(current_id, {})
            styles = current.get("styles") if isinstance(current, dict) else None
            is_non_root = current_id in context.parent_by_child
            if is_non_root and isinstance(styles, dict) and any(
                field in styles for field in ("backgroundColor", "linearGradient")
            ):
                surface_ids.append(current_id)
            current_id = context.parent_by_child.get(current_id)
        if deepest is None or len(surface_ids) > len(deepest[1]):
            deepest = (component_id, surface_ids)

    if deepest is None or len(deepest[1]) <= thresholds.max_nested_surfaces:
        return []
    component_id, surface_ids = deepest
    return [
        diagnostic(
            "warning",
            "AESTHETIC_STYLE_SURFACE_NESTING_EXCESSIVE",
            "内容背板层级过深，卡片出现明显的卡片套卡片风险。",
            json_pointer=f"/updateComponents/components/{context.source_index_by_id[component_id]}",
            actual={"componentId": component_id, "nestedSurfaceIds": surface_ids},
            expected={"maxNestedSurfaces": thresholds.max_nested_surfaces},
            fix_hint="合并相邻背板，将层级收敛为 root 加一个内容面，必要时再保留一个弱分组面。",
        )
    ]


SPACING_TOKENS = frozenset({0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0})


def evaluate_spacing_tokens(context: AestheticContext) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for component in context.components:
        component_id = component.get("id")
        if not isinstance(component_id, str) or not is_effectively_visible(
            component_id, context.components_by_id, context.parent_by_child
        ):
            continue
        for field in ("itemMargin", "space"):
            value = numeric(component.get(field))
            if value is not None and value not in SPACING_TOKENS:
                violations.append(
                    {"componentId": component_id, "field": field, "value": value}
                )
        styles = component.get("styles")
        if not isinstance(styles, dict):
            continue
        for field in ("margin", "padding"):
            for path, value in iter_spacing_numbers(styles.get(field), field):
                if value not in SPACING_TOKENS:
                    violations.append(
                        {"componentId": component_id, "field": path, "value": value}
                    )

    if not violations:
        return []
    return [
        diagnostic(
            "warning",
            "AESTHETIC_LAYOUT_SPACING_NON_TOKEN",
            "间距未落在卡片 spacing token 阶梯内，容易破坏节奏一致性。",
            json_pointer="/updateComponents/components",
            actual={"violations": violations},
            expected={"allowedSpacingTokens": sorted(SPACING_TOKENS)},
            fix_hint="优先使用 4/8/12/16vp；仅在严密预算时使用 2/6/10/14vp。",
        )
    ]


def iter_spacing_numbers(value: object, path: str) -> list[tuple[str, float]]:
    number = numeric(value)
    if number is not None:
        return [(path, number)]
    if isinstance(value, dict):
        results: list[tuple[str, float]] = []
        for key, child in value.items():
            results.extend(iter_spacing_numbers(child, f"{path}.{key}"))
        return results
    return []


def evaluate_repeated_group_spacing(
    context: AestheticContext,
) -> list[dict[str, Any]]:
    """Report only a unique spacing outlier among proven repeated groups.

    A zero gap is not inherently wrong.  This check therefore requires at least
    three visible Row/Column instances with the same static container size,
    child component sequence, child size declarations, alignment and
    distribution.  Exactly one instance must differ from a strict majority.
    """

    groups: dict[tuple[object, ...], list[tuple[str, float]]] = {}
    for component in context.components:
        component_id = component.get("id")
        signature = repeated_container_signature(component, context)
        if not isinstance(component_id, str) or signature is None:
            continue
        if "space" in component:
            continue
        raw_gap = component.get("itemMargin", 0)
        gap = numeric(raw_gap)
        if gap is None:
            continue
        groups.setdefault(signature, []).append((component_id, gap))

    diagnostics: list[dict[str, Any]] = []
    for instances in groups.values():
        if len(instances) < 3:
            continue
        counts: dict[float, int] = {}
        for _, gap in instances:
            counts[gap] = counts.get(gap, 0) + 1
        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        if len(ranked) != 2:
            continue
        expected_gap, expected_count = ranked[0]
        outlier_gap, outlier_count = ranked[1]
        if (
            expected_count != len(instances) - 1
            or expected_count < 2
            or outlier_count != 1
            or expected_gap <= 0
        ):
            continue
        outlier_id = next(
            component_id
            for component_id, gap in instances
            if gap == outlier_gap
        )
        if outlier_gap == 0:
            diagnostics.append(
                diagnostic(
                    "warning",
                    "AESTHETIC_LAYOUT_SPACING_MISSING",
                    "重复组件中唯一一处内部间距缺失，与其余同构组件不一致。",
                    json_pointer=(
                        "/updateComponents/components/"
                        f"{context.source_index_by_id[outlier_id]}/itemMargin"
                    ),
                    actual={
                        "outlierComponentId": outlier_id,
                        "itemMargin": outlier_gap,
                        "peerComponentIds": [
                            component_id
                            for component_id, gap in instances
                            if gap == expected_gap
                        ],
                    },
                    expected={"itemMargin": expected_gap},
                    fix_hint="复用同构组件的 itemMargin；如果此处确需零间距，请拆成不同组件结构以明确设计意图。",
                )
            )
        elif abs(outlier_gap - expected_gap) >= 4:
            diagnostics.append(
                diagnostic(
                    "warning",
                    "AESTHETIC_LAYOUT_SPACING_INCONSISTENT",
                    "重复组件中唯一一处内部间距明显偏离其余同构组件。",
                    json_pointer=(
                        "/updateComponents/components/"
                        f"{context.source_index_by_id[outlier_id]}/itemMargin"
                    ),
                    actual={
                        "outlierComponentId": outlier_id,
                        "itemMargin": outlier_gap,
                        "differenceVp": abs(outlier_gap - expected_gap),
                        "peerComponentIds": [
                            component_id
                            for component_id, gap in instances
                            if gap == expected_gap
                        ],
                    },
                    expected={"itemMargin": expected_gap},
                    fix_hint="复用同构组件的 itemMargin；如果此处需要特殊节奏，请使用不同结构或显式角色标识。",
                )
            )
    return diagnostics


def repeated_container_signature(
    component: dict[str, Any], context: AestheticContext
) -> tuple[object, ...] | None:
    component_id = component.get("id")
    component_type = component.get("component")
    styles = component.get("styles")
    if (
        component_type not in {"Row", "Column"}
        or not isinstance(component_id, str)
        or not isinstance(styles, dict)
        or not is_effectively_visible(
            component_id, context.components_by_id, context.parent_by_child
        )
        or any(field in styles for field in ("layoutWeight", "flexGrow", "flexShrink"))
    ):
        return None
    width, height = numeric(styles.get("width")), numeric(styles.get("height"))
    if width is None or height is None:
        return None
    child_ids = child_component_ids(component)
    if len(child_ids) < 2:
        return None
    child_signatures: list[tuple[object, ...]] = []
    for child_id in child_ids:
        child = context.components_by_id.get(child_id)
        child_styles = child.get("styles") if isinstance(child, dict) else None
        if (
            not isinstance(child, dict)
            or not isinstance(child_styles, dict)
            or not is_effectively_visible(
                child_id, context.components_by_id, context.parent_by_child
            )
            or any(
                field in child_styles
                for field in ("layoutWeight", "flexGrow", "flexShrink")
            )
        ):
            return None
        child_width = numeric(child_styles.get("width"))
        child_height = numeric(child_styles.get("height"))
        if (
            ("width" in child_styles and child_width is None)
            or ("height" in child_styles and child_height is None)
        ):
            return None
        child_signatures.append(
            (
                child.get("component"),
                child_width,
                child_height,
            )
        )
    return (
        component_type,
        width,
        height,
        styles.get("justifyContent"),
        styles.get("alignItems"),
        tuple(child_signatures),
    )


def evaluate_fixed_layout_overflow(context: AestheticContext) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for container in context.components:
        container_id = container.get("id")
        container_type = container.get("component")
        styles = container.get("styles")
        if (
            container_type not in {"Row", "Column", "List"}
            or not isinstance(container_id, str)
            or not isinstance(styles, dict)
            or not is_effectively_visible(
                container_id, context.components_by_id, context.parent_by_child
            )
        ):
            continue
        axis = static_container_main_axis(container, context)
        if axis is None:
            continue
        available = static_component_dimension(container, axis, context)
        if available is None:
            continue
        padding = spacing_axis_total(styles.get("padding"), axis)
        if padding is None:
            continue
        available -= padding
        child_sizes: list[float] = []
        unresolved = False
        children = child_component_ids(container)
        for child_id in children:
            child = context.components_by_id.get(child_id, {})
            child_styles = child.get("styles") if isinstance(child, dict) else None
            if not isinstance(child_styles, dict) or any(
                field in child_styles for field in ("layoutWeight", "flexShrink", "flexGrow")
            ):
                unresolved = True
                break
            child_size = numeric(child_styles.get(axis))
            margin = spacing_axis_total(child_styles.get("margin"), axis)
            if child_size is None or margin is None:
                unresolved = True
                break
            child_sizes.append(child_size + margin)
        if unresolved or not child_sizes:
            continue
        if (
            container_type == "Column"
            and children
            and all(
                subtree_contains_action(child_id, context, set())
                for child_id in children
            )
        ):
            continue
        gap = numeric(container.get("itemMargin"))
        if gap is None:
            if "itemMargin" in container:
                continue
            gap = 0.0
        required = sum(child_sizes) + gap * (len(child_sizes) - 1)
        overflow = required - available
        minimum_overflow = MIN_PROVABLE_FIXED_OVERFLOW_VP
        if container_id == context.root_id and container_type == "Column":
            minimum_overflow = MIN_PROVABLE_ROOT_COLUMN_OVERFLOW_VP
        if overflow + 1e-9 >= minimum_overflow:
            diagnostics.append(
                diagnostic(
                    "warning",
                    "AESTHETIC_LAYOUT_BOUNDS_OVERFLOW",
                    "固定尺寸子项超过容器可用空间，存在内容截断、溢出或挤压风险。",
                    json_pointer=f"/updateComponents/components/{context.source_index_by_id[container_id]}",
                    actual={
                        "containerId": container_id,
                        "axis": axis,
                        "available": available,
                        "required": required,
                        "overflow": overflow,
                        "minimumReportableOverflow": minimum_overflow,
                        "childSizes": child_sizes,
                        "itemMargin": gap,
                    },
                    expected={"required": f"<= {available}"},
                    fix_hint="缩短固定尺寸、减少间距，或改用已验证的弹性布局并在真实渲染中复核。",
                )
            )
    return diagnostics


def static_container_main_axis(
    container: dict[str, Any], context: AestheticContext
) -> str | None:
    component_type = container.get("component")
    if component_type == "Row":
        return "width"
    if component_type == "Column":
        return "height"
    if component_type != "List":
        return None
    styles = container.get("styles")
    list_direction = styles.get("listDirection") if isinstance(styles, dict) else None
    if list_direction == "horizontal":
        return None
    if list_direction == "vertical":
        return "height"
    child_types = {
        context.components_by_id.get(child_id, {}).get("component")
        for child_id in child_component_ids(container)
    }
    # In this GenUI corpus, Row children form a vertical list. Column children
    # form a horizontal list/carousel whose overflow is intentional scrolling.
    return "height" if child_types == {"Row"} else None


def evaluate_adjacent_control_clearance(
    context: AestheticContext,
) -> list[dict[str, Any]]:
    """Report statically proven gaps below 2vp between rounded controls/surfaces."""

    diagnostics: list[dict[str, Any]] = []
    minimum_gap = 2.0
    distributed_alignment = {"spaceBetween", "spaceAround", "spaceEvenly"}
    for container in context.components:
        container_id = container.get("id")
        container_type = container.get("component")
        styles = container.get("styles")
        children = child_component_ids(container)
        if (
            container_type not in {"Row", "Column", "List"}
            or not isinstance(container_id, str)
            or not isinstance(styles, dict)
            or len(children) < 2
            or styles.get("justifyContent") in distributed_alignment
            or not is_effectively_visible(
                container_id, context.components_by_id, context.parent_by_child
            )
        ):
            continue
        raw_gap = container.get("itemMargin", 0)
        gap = numeric(raw_gap)
        if gap is None:
            continue
        dimension = static_container_main_axis(container, context)
        if dimension is None:
            continue
        axis = "horizontal" if dimension == "width" else "vertical"
        crowded_pairs: list[dict[str, Any]] = []
        for first_id, second_id in zip(children, children[1:]):
            first = context.components_by_id.get(first_id, {})
            second = context.components_by_id.get(second_id, {})
            if not (
                is_rounded_control_or_surface(first)
                and is_rounded_control_or_surface(second)
            ):
                continue
            first_styles = first.get("styles")
            second_styles = second.get("styles")
            first_margin = spacing_sides(
                first_styles.get("margin") if isinstance(first_styles, dict) else None
            )
            second_margin = spacing_sides(
                second_styles.get("margin") if isinstance(second_styles, dict) else None
            )
            if first_margin is None or second_margin is None:
                continue
            if axis == "horizontal":
                actual_gap = gap + first_margin[1] + second_margin[3]
            else:
                actual_gap = gap + first_margin[2] + second_margin[0]
            if actual_gap + 1e-9 >= minimum_gap:
                continue
            crowded_pairs.append(
                {
                    "firstId": first_id,
                    "secondId": second_id,
                    "gap": actual_gap,
                }
            )
        if not crowded_pairs:
            continue
        diagnostics.append(
            diagnostic(
                "warning",
                "AESTHETIC_CONTROL_GROUP_GAP_LOW",
                "相邻圆角控件或表面之间缺少可辨的背景间隔，边缘容易黏连。",
                json_pointer=(
                    "/updateComponents/components/"
                    f"{context.source_index_by_id[container_id]}"
                ),
                actual={
                    "containerId": container_id,
                    "axis": axis,
                    "itemMargin": gap,
                    "minimumAdjacentGap": min(
                        pair["gap"] for pair in crowded_pairs
                    ),
                    "crowdedPairs": crowded_pairs,
                },
                expected={"minimumGap": minimum_gap},
                fix_hint="将相邻胶囊、按钮或圆角行的有效间距增加到至少 2vp。",
            )
        )
    return diagnostics


def evaluate_adjacent_text_clearance(
    context: AestheticContext,
) -> list[dict[str, Any]]:
    """Detect large CJK ink that cannot stay clear of the following text line."""

    diagnostics: list[dict[str, Any]] = []
    minimum_gap = 4.0
    for container in context.components:
        container_id = container.get("id")
        styles = container.get("styles")
        children = child_component_ids(container)
        if (
            container.get("component") != "Column"
            or not isinstance(container_id, str)
            or not isinstance(styles, dict)
            or len(children) < 2
            or not is_effectively_visible(
                container_id, context.components_by_id, context.parent_by_child
            )
        ):
            continue
        gap = numeric(container.get("itemMargin", 0))
        if gap is None:
            continue
        for first_id, second_id in zip(children, children[1:]):
            first = context.components_by_id.get(first_id, {})
            second = context.components_by_id.get(second_id, {})
            first_styles = first.get("styles")
            second_styles = second.get("styles")
            if (
                first.get("component") != "Text"
                or second.get("component") != "Text"
                or not isinstance(first_styles, dict)
                or not isinstance(second_styles, dict)
            ):
                continue
            first_font_size = numeric(first_styles.get("fontSize"))
            first_height = numeric(first_styles.get("height"))
            first_text = resolve_visible_text(first, context)
            first_margin = spacing_sides(first_styles.get("margin"))
            second_margin = spacing_sides(second_styles.get("margin"))
            if (
                first_font_size is None
                or first_font_size < 20.0
                or first_height is None
                or first_height + 1e-9 >= first_font_size
                or first_text is None
                or not contains_cjk(first_text)
                or first_margin is None
                or second_margin is None
            ):
                continue
            actual_gap = gap + first_margin[2] + second_margin[0]
            if actual_gap + 1e-9 >= minimum_gap:
                continue
            collision = actual_gap <= 0 and is_all_cjk_text(first_text)
            diagnostics.append(
                diagnostic(
                    "warning",
                    (
                        "AESTHETIC_TEXT_COLLISION_RISK"
                        if collision
                        else "AESTHETIC_TEXT_GAP_LOW"
                    ),
                    (
                        "大字号中文的固定高度小于字号，且与下一行零间距，字形绘制边界存在相交风险。"
                        if collision
                        else "大字号中文文字的固定高度小于字号，且与下一行文字缺少安全间隔。"
                    ),
                    json_pointer=(
                        "/updateComponents/components/"
                        f"{context.source_index_by_id[container_id]}"
                    ),
                    actual={
                        "containerId": container_id,
                        "firstId": first_id,
                        "secondId": second_id,
                        "fontSize": first_font_size,
                        "textBoxHeight": first_height,
                        "gap": actual_gap,
                    },
                    expected={
                        "textBoxHeight": f">= {first_font_size}",
                        "minimumGap": minimum_gap,
                    },
                    fix_hint="增加大字号文字框高度和下一行前的 itemMargin，避免两行字形黏连。",
                )
            )
    return diagnostics


def contains_cjk(text: str) -> bool:
    return any(
        "\u3400" <= character <= "\u9fff"
        or "\uf900" <= character <= "\ufaff"
        for character in text
    )


def is_all_cjk_text(text: str) -> bool:
    visible = [character for character in text.strip() if not character.isspace()]
    return bool(visible) and all(
        "\u3400" <= character <= "\u9fff"
        or "\uf900" <= character <= "\ufaff"
        for character in visible
    )


def is_rounded_control_or_surface(component: dict[str, Any]) -> bool:
    styles = component.get("styles")
    if not isinstance(styles, dict):
        return False
    component_type = component.get("component")
    radius = numeric(styles.get("borderRadius"))
    if component_type == "Checkbox":
        return True
    if radius is None or radius <= 0:
        return False
    return component_type == "Button" or any(
        field in styles
        for field in ("backgroundColor", "linearGradient", "borderColor", "borderWidth")
    )


def evaluate_intrinsic_control_clearance(
    context: AestheticContext,
) -> list[dict[str, Any]]:
    """Account for the 20vp visible paint box of compact Checkbox controls."""

    diagnostics: list[dict[str, Any]] = []
    minimum_gap = 2.0
    for container in context.components:
        container_id = container.get("id")
        container_type = container.get("component")
        styles = container.get("styles")
        children = child_component_ids(container)
        if (
            container_type not in {"Row", "Column", "List"}
            or not isinstance(container_id, str)
            or not isinstance(styles, dict)
            or len(children) < 2
            or not is_effectively_visible(
                container_id, context.components_by_id, context.parent_by_child
            )
        ):
            continue
        gap = numeric(container.get("itemMargin", 0))
        if gap is None:
            continue
        dimension = static_container_main_axis(container, context)
        if dimension is None:
            continue
        if container_type == "Row" and styles.get("justifyContent") == "spaceBetween":
            container_width = static_component_dimension(
                container, "width", context
            )
            padding = spacing_sides(styles.get("padding"))
            occupied_width = 0.0
            if container_width is None or padding is None:
                continue
            distributed_resolved = True
            for child_id in children:
                child = context.components_by_id.get(child_id, {})
                child_styles = child.get("styles")
                child_width = static_component_dimension(child, "width", context)
                margins = spacing_sides(
                    child_styles.get("margin")
                    if isinstance(child_styles, dict)
                    else None
                )
                if child_width is None or margins is None:
                    distributed_resolved = False
                    break
                occupied_width += margins[3] + child_width + margins[1]
            if not distributed_resolved:
                continue
            distributed_gap = (
                container_width - padding[3] - padding[1] - occupied_width
            ) / (len(children) - 1)
            if distributed_gap + 1e-9 < gap:
                continue
            gap = distributed_gap
        crowded_pairs: list[dict[str, Any]] = []
        for first_id, second_id in zip(children, children[1:]):
            first = context.components_by_id.get(first_id, {})
            second = context.components_by_id.get(second_id, {})
            first_styles = first.get("styles")
            second_styles = second.get("styles")
            if not isinstance(first_styles, dict) or not isinstance(second_styles, dict):
                continue
            first_size = numeric(first_styles.get(dimension))
            second_size = numeric(second_styles.get(dimension))
            first_paint = compact_checkbox_paint_extent(
                first_id, dimension, context, set()
            )
            second_paint = compact_checkbox_paint_extent(
                second_id, dimension, context, set()
            )
            first_margin = spacing_sides(first_styles.get("margin"))
            second_margin = spacing_sides(second_styles.get("margin"))
            if (
                first_size is None
                or second_size is None
                or first_paint is None
                or second_paint is None
                or first_margin is None
                or second_margin is None
            ):
                continue
            first_overhang = max(first_paint - first_size, 0.0) / 2.0
            second_overhang = max(second_paint - second_size, 0.0) / 2.0
            if first_overhang <= 0 and second_overhang <= 0:
                continue
            if dimension == "width":
                box_gap = gap + first_margin[1] + second_margin[3]
            else:
                box_gap = gap + first_margin[2] + second_margin[0]
            painted_gap = box_gap - first_overhang - second_overhang
            if painted_gap + 1e-9 >= minimum_gap:
                continue
            crowded_pairs.append(
                {
                    "firstId": first_id,
                    "secondId": second_id,
                    "boxGap": box_gap,
                    "paintedGap": painted_gap,
                    "firstPaintExtent": first_paint,
                    "secondPaintExtent": second_paint,
                }
            )
        if not crowded_pairs:
            continue
        diagnostics.append(
            diagnostic(
                "warning",
                "AESTHETIC_CONTROL_INTRINSIC_GAP_LOW",
                "复选框的固有绘制尺寸超出声明布局盒，压缩了相邻控件的实际可见间距。",
                json_pointer=(
                    "/updateComponents/components/"
                    f"{context.source_index_by_id[container_id]}"
                ),
                actual={
                    "containerId": container_id,
                    "axis": dimension,
                    "checkboxIntrinsicSize": CHECKBOX_INTRINSIC_SIZE_VP,
                    "paintedGap": min(
                        pair["paintedGap"] for pair in crowded_pairs
                    ),
                    "crowdedPairs": crowded_pairs,
                },
                expected={"minimumGap": minimum_gap},
                fix_hint="为 20×20vp 可见复选框内盒预留真实布局尺寸，并增加相邻行列之间的有效间距。",
            )
        )
    return diagnostics


def compact_checkbox_paint_extent(
    component_id: str,
    dimension: str,
    context: AestheticContext,
    visited: set[str],
) -> float | None:
    if component_id in visited:
        return None
    visited.add(component_id)
    component = context.components_by_id.get(component_id, {})
    styles = component.get("styles")
    if not isinstance(styles, dict):
        return None
    declared = numeric(styles.get(dimension))
    if declared is None:
        return None
    if component.get("component") == "Checkbox":
        width = numeric(styles.get("width"))
        height = numeric(styles.get("height"))
        if (
            width is None
            or height is None
            or width > CHECKBOX_INTRINSIC_SIZE_VP
            or height > CHECKBOX_INTRINSIC_SIZE_VP
        ):
            return declared
        return max(declared, CHECKBOX_INTRINSIC_SIZE_VP)

    component_type = component.get("component")
    cross_axis = (
        component_type == "Row" and dimension == "height"
    ) or (
        component_type == "Column" and dimension == "width"
    )
    if not cross_axis or styles.get("alignItems") != "center":
        return declared
    child_extents = [
        extent
        for child_id in child_component_ids(component)
        if (
            extent := compact_checkbox_paint_extent(
                child_id, dimension, context, visited.copy()
            )
        )
        is not None
    ]
    return max([declared, *child_extents])


def evaluate_text_icon_clearance(
    context: AestheticContext,
) -> list[dict[str, Any]]:
    """Check direct Text/icon siblings only when their static gap is below 4vp."""

    diagnostics: list[dict[str, Any]] = []
    minimum_gap = 4.0
    icon_types = {"Image", "Checkbox", "SymbolGlyph", "Icon"}
    for container in context.components:
        container_id = container.get("id")
        styles = container.get("styles")
        children = child_component_ids(container)
        if (
            container.get("component") != "Row"
            or not isinstance(container_id, str)
            or not isinstance(styles, dict)
            or len(children) < 2
            or not is_effectively_visible(
                container_id, context.components_by_id, context.parent_by_child
            )
        ):
            continue
        item_gap = numeric(container.get("itemMargin", 0))
        if item_gap is None:
            continue
        if styles.get("justifyContent") == "spaceBetween":
            container_width = static_component_dimension(
                container, "width", context
            )
            container_padding = spacing_sides(styles.get("padding"))
            occupied_width = 0.0
            distributed_resolved = (
                container_width is not None and container_padding is not None
            )
            if distributed_resolved:
                for child_id in children:
                    child = context.components_by_id.get(child_id, {})
                    child_styles = child.get("styles")
                    child_width = static_component_dimension(
                        child, "width", context
                    )
                    child_margin = spacing_sides(
                        child_styles.get("margin")
                        if isinstance(child_styles, dict)
                        else None
                    )
                    if child_width is None or child_margin is None:
                        distributed_resolved = False
                        break
                    occupied_width += (
                        child_margin[3] + child_width + child_margin[1]
                    )
            if not distributed_resolved or container_padding is None:
                continue
            inner_width = (
                container_width
                - container_padding[3]
                - container_padding[1]
            )
            distributed_gap = (inner_width - occupied_width) / (
                len(children) - 1
            )
            if distributed_gap + 1e-9 < item_gap:
                continue
            item_gap = distributed_gap
        crowded_pairs: list[dict[str, Any]] = []
        for first_id, second_id in zip(children, children[1:]):
            first = context.components_by_id.get(first_id, {})
            second = context.components_by_id.get(second_id, {})
            if not (
                is_effectively_visible(
                    first_id, context.components_by_id, context.parent_by_child
                )
                and is_effectively_visible(
                    second_id, context.components_by_id, context.parent_by_child
                )
            ):
                continue
            pair_types = {first.get("component"), second.get("component")}
            if "Text" not in pair_types or not (pair_types & icon_types):
                continue
            first_styles = first.get("styles")
            second_styles = second.get("styles")
            first_margin = spacing_sides(
                first_styles.get("margin") if isinstance(first_styles, dict) else None
            )
            second_margin = spacing_sides(
                second_styles.get("margin") if isinstance(second_styles, dict) else None
            )
            if first_margin is None or second_margin is None:
                continue
            paint_overhang = 0.0
            checkbox = next(
                (
                    item
                    for item in (first, second)
                    if item.get("component") == "Checkbox"
                ),
                None,
            )
            checkbox_styles = checkbox.get("styles") if checkbox else None
            if checkbox is not None and isinstance(checkbox_styles, dict):
                checkbox_width = numeric(checkbox_styles.get("width"))
                checkbox_height = numeric(checkbox_styles.get("height"))
                if (
                    checkbox_width is not None
                    and checkbox_height is not None
                    and checkbox_width <= 16.0
                    and checkbox_height <= 16.0
                ):
                    paint_overhang = max(
                        0.0, CHECKBOX_INTRINSIC_SIZE_VP - checkbox_width
                    )
            actual_gap = (
                item_gap + first_margin[1] + second_margin[3] - paint_overhang
            )
            if actual_gap + 1e-9 >= minimum_gap:
                continue
            crowded_pairs.append(
                {
                    "firstId": first_id,
                    "secondId": second_id,
                    "gap": actual_gap,
                    "paintOverhang": paint_overhang,
                }
            )
        if not crowded_pairs:
            continue
        diagnostics.append(
            diagnostic(
                "warning",
                "AESTHETIC_TEXT_ICON_GAP_LOW",
                "文字与相邻图标或勾选框之间缺少可辨的背景间隔。",
                json_pointer=(
                    "/updateComponents/components/"
                    f"{context.source_index_by_id[container_id]}"
                ),
                actual={
                    "containerId": container_id,
                    "gap": min(pair["gap"] for pair in crowded_pairs),
                    "crowdedPairs": crowded_pairs,
                },
                expected={"minimumGap": minimum_gap},
                fix_hint="将文字与图标、勾选框之间的有效间距增加到至少 4vp。",
            )
        )
    return diagnostics


def assess_checkbox_text_clearance(
    context: AestheticContext,
    diagnostics: list[dict[str, Any]],
) -> dict[str, Any]:
    icon_types = {"Image", "Checkbox", "SymbolGlyph", "Icon"}
    candidate_ids: list[str] = []
    unresolved_reasons: list[str] = []
    for container in context.components:
        container_id = container.get("id")
        styles = container.get("styles")
        children = child_component_ids(container)
        if (
            container.get("component") != "Row"
            or not isinstance(container_id, str)
            or not isinstance(styles, dict)
            or len(children) < 2
            or not is_effectively_visible(
                container_id, context.components_by_id, context.parent_by_child
            )
        ):
            continue
        relevant_pairs: list[tuple[str, str]] = []
        for first_id, second_id in zip(children, children[1:]):
            first = context.components_by_id.get(first_id, {})
            second = context.components_by_id.get(second_id, {})
            pair_types = {first.get("component"), second.get("component")}
            if (
                "Text" in pair_types
                and pair_types & icon_types
                and is_effectively_visible(
                    first_id, context.components_by_id, context.parent_by_child
                )
                and is_effectively_visible(
                    second_id, context.components_by_id, context.parent_by_child
                )
            ):
                relevant_pairs.append((first_id, second_id))
        if not relevant_pairs:
            continue
        candidate_ids.append(container_id)
        if numeric(container.get("itemMargin", 0)) is None:
            unresolved_reasons.append(
                f"{container_id}: itemMargin 无法静态求解"
            )
        justify = styles.get("justifyContent", "start")
        if justify in {"spaceAround", "spaceEvenly"}:
            unresolved_reasons.append(
                f"{container_id}: justifyContent={justify!r} 尚未建模"
            )
        elif justify == "spaceBetween":
            if (
                static_component_dimension(container, "width", context) is None
                or spacing_sides(styles.get("padding")) is None
            ):
                unresolved_reasons.append(
                    f"{container_id}: spaceBetween 容器宽度或 padding 无法求解"
                )
            for child_id in children:
                child = context.components_by_id.get(child_id, {})
                child_styles = child.get("styles")
                if (
                    static_component_dimension(child, "width", context) is None
                    or spacing_sides(
                        child_styles.get("margin")
                        if isinstance(child_styles, dict)
                        else None
                    )
                    is None
                ):
                    unresolved_reasons.append(
                        f"{container_id}/{child_id}: spaceBetween 子项宽度或 margin 无法求解"
                    )
                    break
        for first_id, second_id in relevant_pairs:
            first = context.components_by_id.get(first_id, {})
            second = context.components_by_id.get(second_id, {})
            for item_id, item in ((first_id, first), (second_id, second)):
                item_styles = item.get("styles")
                if spacing_sides(
                    item_styles.get("margin")
                    if isinstance(item_styles, dict)
                    else None
                ) is None:
                    unresolved_reasons.append(
                        f"{container_id}/{item_id}: margin 无法静态求解"
                    )
            checkbox = next(
                (
                    item
                    for item in (first, second)
                    if item.get("component") == "Checkbox"
                ),
                None,
            )
            if checkbox is not None:
                checkbox_styles = checkbox.get("styles")
                if (
                    not isinstance(checkbox_styles, dict)
                    or numeric(checkbox_styles.get("width")) is None
                    or numeric(checkbox_styles.get("height")) is None
                ):
                    unresolved_reasons.append(
                        f"{container_id}: Checkbox 绘制宽高无法静态求解"
                    )

    if diagnostics:
        return rule_assessment(
            "checkbox_text_clearance",
            "issue",
            "proven_static_geometry",
            component_ids=candidate_ids,
            reasons=unresolved_reasons,
        )
    if not candidate_ids:
        return rule_assessment(
            "checkbox_text_clearance", "not_applicable", "structural"
        )
    if unresolved_reasons:
        return rule_assessment(
            "checkbox_text_clearance",
            "undetermined",
            "unknown_geometry",
            component_ids=candidate_ids,
            reasons=unresolved_reasons,
        )
    return rule_assessment(
        "checkbox_text_clearance",
        "clear",
        "proven_static_geometry",
        component_ids=candidate_ids,
    )


def evaluate_vertical_text_stack_density(
    context: AestheticContext,
    excluded_container_ids: set[object] | None = None,
) -> list[dict[str, Any]]:
    """Check fixed-height columns whose direct text lines leave no breathing room."""

    diagnostics: list[dict[str, Any]] = []
    excluded_container_ids = excluded_container_ids or set()
    for container in context.components:
        container_id = container.get("id")
        styles = container.get("styles")
        children = child_component_ids(container)
        if (
            container.get("component") != "Column"
            or not isinstance(container_id, str)
            or container_id in excluded_container_ids
            or not isinstance(styles, dict)
            or len(children) < 3
            or not is_effectively_visible(
                container_id, context.components_by_id, context.parent_by_child
            )
        ):
            continue
        height = static_component_dimension(container, "height", context)
        padding = spacing_sides(styles.get("padding"))
        if height is None or padding is None:
            continue
        top, _, bottom, _ = padding
        line_heights: list[float] = []
        unresolved = False
        for child_id in children:
            child = context.components_by_id.get(child_id, {})
            child_styles = child.get("styles") if isinstance(child, dict) else None
            if (
                child.get("component") != "Text"
                or not isinstance(child_styles, dict)
                or child_styles.get("maxLines", 1) != 1
            ):
                unresolved = True
                break
            font_size = numeric(child_styles.get("fontSize"))
            margin = spacing_sides(child_styles.get("margin"))
            if font_size is None or margin is None:
                unresolved = True
                break
            child_top, _, child_bottom, _ = margin
            line_heights.append(font_size + child_top + child_bottom)
        if unresolved:
            continue
        gap = numeric(container.get("itemMargin"))
        if gap is None:
            if "itemMargin" in container:
                continue
            gap = 0.0
        available = height - top - bottom
        required = sum(line_heights) + gap * (len(line_heights) - 1)
        free_space = available - required
        has_surface = any(
            field in styles
            for field in (
                "backgroundColor",
                "linearGradient",
                "borderColor",
                "borderWidth",
            )
        )
        minimum_breathing = 8.0 if has_surface else 0.0
        if not has_surface and free_space < 0:
            minimum_breathing = -MIN_PROVABLE_NON_SURFACE_TEXT_STACK_OVERFLOW_VP
        if free_space + 1e-9 >= minimum_breathing:
            continue
        diagnostics.append(
            diagnostic(
                "warning",
                "AESTHETIC_LAYOUT_VERTICAL_DENSITY_HIGH",
                "多行文字占满固定高度区域，顶部和底部缺少必要留白。",
                json_pointer=(
                    "/updateComponents/components/"
                    f"{context.source_index_by_id[container_id]}"
                ),
                actual={
                    "containerId": container_id,
                    "lineCount": len(line_heights),
                    "availableHeight": available,
                    "requiredTextHeight": required,
                    "verticalFreeSpace": free_space,
                    "topPadding": top,
                    "bottomPadding": bottom,
                    "itemMargin": gap,
                },
                expected={"minimumVerticalBreathing": minimum_breathing},
                fix_hint="增加面板上下 padding 或高度，并给相邻文字行保留稳定的垂直间距。",
            )
        )
    return diagnostics


def static_component_dimension(
    component: dict[str, Any], axis: str, context: AestheticContext
) -> float | None:
    styles = component.get("styles")
    if not isinstance(styles, dict):
        return None
    value = numeric(styles.get(axis))
    if value is not None:
        return value
    if (
        component.get("id") == context.root_id
        and styles.get(axis) == "matchParent"
    ):
        return context.surface_width if axis == "width" else context.surface_height
    return None


def estimate_static_layout(context: AestheticContext) -> StaticLayoutEstimate | None:
    root = context.components_by_id.get(context.root_id, {})
    root_width, root_width_source = estimated_component_dimension(
        root, "width", context
    )
    root_height, root_height_source = estimated_component_dimension(
        root, "height", context
    )
    if root_width is None or root_height is None:
        return None

    rect_by_id: dict[str, tuple[float, float, float, float]] = {}
    dimension_source_by_id: dict[str, tuple[str, str]] = {}
    unresolved_reasons: list[str] = []

    def layout_component(
        component_id: str,
        rect: tuple[float, float, float, float],
        width_source: str,
        height_source: str,
        visited: set[str],
    ) -> None:
        if component_id in visited:
            unresolved_reasons.append(f"{component_id}: 布局树存在循环")
            return
        visited.add(component_id)
        component = context.components_by_id.get(component_id, {})
        if not is_effectively_visible(
            component_id, context.components_by_id, context.parent_by_child
        ):
            return
        rect_by_id[component_id] = rect
        dimension_source_by_id[component_id] = (width_source, height_source)

        component_type = component.get("component")
        if component_type not in {"Row", "Column", "Stack"}:
            return
        styles = component.get("styles")
        if not isinstance(styles, dict):
            unresolved_reasons.append(f"{component_id}: styles 无法静态求解")
            return
        padding = spacing_sides(styles.get("padding"))
        if padding is None:
            unresolved_reasons.append(f"{component_id}: padding 无法静态求解")
            return
        top, right, bottom, left = padding
        x, y, width, height = rect
        inner = (
            x + left,
            y + top,
            width - left - right,
            height - top - bottom,
        )
        if inner[2] <= 0 or inner[3] <= 0:
            unresolved_reasons.append(f"{component_id}: 内容框无效")
            return
        children = child_component_ids(component)
        if not children:
            return

        child_specs: list[
            tuple[
                str,
                float,
                float,
                str,
                str,
                tuple[float, float, float, float],
            ]
        ] = []
        for child_id in children:
            child = context.components_by_id.get(child_id, {})
            if not is_effectively_visible(
                child_id, context.components_by_id, context.parent_by_child
            ):
                continue
            child_styles = child.get("styles")
            margins = spacing_sides(
                child_styles.get("margin")
                if isinstance(child_styles, dict)
                else None
            )
            child_width, child_width_source = estimated_component_dimension(
                child, "width", context
            )
            child_height, child_height_source = estimated_component_dimension(
                child, "height", context
            )
            if child_width is None or child_height is None or margins is None:
                unresolved_reasons.append(
                    f"{component_id}/{child_id}: 子项尺寸或 margin 无法静态求解"
                )
                return
            child_specs.append(
                (
                    child_id,
                    child_width,
                    child_height,
                    child_width_source,
                    child_height_source,
                    margins,
                )
            )
        if not child_specs:
            return

        if component_type == "Stack":
            alignment = styles.get("alignContent", "center")
            for (
                child_id,
                child_width,
                child_height,
                child_width_source,
                child_height_source,
                margins,
            ) in child_specs:
                child_rect = static_stack_child_rect(
                    inner, child_width, child_height, margins, alignment
                )
                if child_rect is None:
                    unresolved_reasons.append(
                        f"{component_id}: alignContent={alignment!r} 无法静态求解"
                    )
                    return
                layout_component(
                    child_id,
                    child_rect,
                    child_width_source,
                    child_height_source,
                    visited.copy(),
                )
            return

        item_margin = numeric(component.get("itemMargin"))
        if item_margin is None:
            if "itemMargin" in component:
                unresolved_reasons.append(
                    f"{component_id}: itemMargin 无法静态求解"
                )
                return
            item_margin = 0.0

        is_row = component_type == "Row"
        occupied_main = [
            (
                margins[3] + child_width + margins[1]
                if is_row
                else margins[0] + child_height + margins[2]
            )
            for _, child_width, child_height, _, _, margins in child_specs
        ]
        main_origin = inner[0] if is_row else inner[1]
        main_size = inner[2] if is_row else inner[3]
        justify = styles.get("justifyContent", "start")
        if justify in {"start", "flex-start", "top", "left", None}:
            gap = item_margin
            cursor = main_origin
        elif justify == "center":
            gap = item_margin
            total = sum(occupied_main) + gap * (len(child_specs) - 1)
            cursor = main_origin + (main_size - total) / 2.0
        elif justify in {"end", "flex-end", "bottom", "right"}:
            gap = item_margin
            total = sum(occupied_main) + gap * (len(child_specs) - 1)
            cursor = main_origin + main_size - total
        elif justify == "spaceBetween" and len(child_specs) > 1:
            gap = (main_size - sum(occupied_main)) / (len(child_specs) - 1)
            cursor = main_origin
        else:
            unresolved_reasons.append(
                f"{component_id}: justifyContent={justify!r} 无法静态求解"
            )
            return

        align = styles.get("alignItems", "start")
        for (
            child_id,
            child_width,
            child_height,
            child_width_source,
            child_height_source,
            margins,
        ) in child_specs:
            child_top, child_right, child_bottom, child_left = margins
            occupied_width = child_left + child_width + child_right
            occupied_height = child_top + child_height + child_bottom
            if is_row:
                child_x = cursor + child_left
                if align in {"start", "flex-start", "top", "left", None}:
                    child_y = inner[1] + child_top
                elif align == "center":
                    child_y = inner[1] + (inner[3] - occupied_height) / 2.0 + child_top
                elif align in {"end", "flex-end", "bottom", "right"}:
                    child_y = inner[1] + inner[3] - occupied_height + child_top
                else:
                    unresolved_reasons.append(
                        f"{component_id}: alignItems={align!r} 无法静态求解"
                    )
                    return
                cursor += occupied_width + gap
            else:
                child_y = cursor + child_top
                if align in {"start", "flex-start", "top", "left", None}:
                    child_x = inner[0] + child_left
                elif align == "center":
                    child_x = inner[0] + (inner[2] - occupied_width) / 2.0 + child_left
                elif align in {"end", "flex-end", "bottom", "right"}:
                    child_x = inner[0] + inner[2] - occupied_width + child_left
                else:
                    unresolved_reasons.append(
                        f"{component_id}: alignItems={align!r} 无法静态求解"
                    )
                    return
                cursor += occupied_height + gap
            layout_component(
                child_id,
                (child_x, child_y, child_width, child_height),
                child_width_source,
                child_height_source,
                visited.copy(),
            )

    layout_component(
        context.root_id,
        (0.0, 0.0, root_width, root_height),
        root_width_source,
        root_height_source,
        set(),
    )
    return StaticLayoutEstimate(
        rect_by_id=rect_by_id,
        dimension_source_by_id=dimension_source_by_id,
        unresolved_reasons=unresolved_reasons,
    )


def estimated_component_dimension(
    component: dict[str, Any], axis: str, context: AestheticContext
) -> tuple[float | None, str]:
    value = static_component_dimension(component, axis, context)
    if value is not None:
        return value, "static"
    styles = component.get("styles")
    if not isinstance(styles, dict):
        return None, "unknown"
    if axis == "height" and component.get("component") in {"Text", "Button"}:
        raw_text = visible_text_value(component)
        if raw_text is None:
            return None, "unknown"
        max_lines = static_max_lines(styles)
        if max_lines is None or max_lines <= 0:
            return None, "unknown"
        font_size = numeric(styles.get("fontSize"))
        if font_size is None:
            font_size = 16.0
        vertical_padding = spacing_axis_total(styles.get("padding"), "height")
        if vertical_padding is None:
            return None, "unknown"
        line_height = font_size * ESTIMATED_TEXT_LINE_HEIGHT_RATIO
        return (
            math.ceil(line_height * max_lines + vertical_padding),
            "estimated_text_line_height",
        )
    return None, "unknown"


def evaluate_rounded_surface_root_edge_safety(
    context: AestheticContext,
) -> list[dict[str, Any]]:
    layout = estimate_static_layout(context)
    if layout is None:
        return []
    root = context.components_by_id.get(context.root_id, {})
    root_styles = root.get("styles")
    root_radius = (
        numeric(root_styles.get("borderRadius"))
        if isinstance(root_styles, dict)
        else None
    )
    if (
        root_radius is None
        or root_radius < 16.0
        or not rounded_visual_surface_candidate(root)
        or context.root_id not in layout.rect_by_id
    ):
        return []
    root_rect = layout.rect_by_id[context.root_id]
    root_padding = (
        spacing_sides(root_styles.get("padding"))
        if isinstance(root_styles, dict)
        else None
    )
    if root_padding is None:
        return []
    root_x, _, root_width, _ = root_rect
    _, root_right_padding, _, root_left_padding = root_padding
    root_content_x = root_x + root_left_padding
    root_content_width = root_width - root_left_padding - root_right_padding
    _, root_y, _, root_height = root_rect
    root_top_padding, _, root_bottom_padding, _ = root_padding
    root_content_y = root_y + root_top_padding
    root_content_height = root_height - root_top_padding - root_bottom_padding
    if root_content_width <= 0 or root_content_height <= 0:
        return []

    crowded_items: list[dict[str, Any]] = []
    for component in context.components:
        component_id = component.get("id")
        if (
            not isinstance(component_id, str)
            or component_id == context.root_id
            or component_id not in layout.rect_by_id
            or not rounded_visual_surface_candidate(component)
            or not is_effectively_visible(
                component_id, context.components_by_id, context.parent_by_child
            )
        ):
            continue
        x, y, width, height = layout.rect_by_id[component_id]
        if min(width, height) + 1e-9 < 24.0:
            continue
        left_content_clearance = x - root_content_x
        top_content_clearance = y - root_content_y
        right_content_clearance = (
            root_content_x + root_content_width - x - width
        )
        bottom_content_clearance = (
            root_content_y + root_content_height - y - height
        )
        content_clearances = {
            "left": left_content_clearance,
            "top": top_content_clearance,
            "right": right_content_clearance,
            "bottom": bottom_content_clearance,
        }
        flush_edges = [
            edge
            for edge, clearance in content_clearances.items()
            if abs(clearance) <= ROOT_ACTION_CONTENT_FILL_EPSILON_VP
        ]
        contact_issue = root_content_edge_contact_issue(
            component_id,
            component,
            width,
            height,
            root_content_width,
            root_content_height,
            flush_edges,
            context,
            layout,
            (root_content_x, root_content_y, root_content_width, root_content_height),
        )
        if contact_issue is None:
            continue
        component_styles = component.get("styles")
        component_radius = (
            numeric(component_styles.get("borderRadius"))
            if isinstance(component_styles, dict)
            else None
        )
        width_source, height_source = layout.dimension_source_by_id.get(
            component_id, ("unknown", "unknown")
        )
        crowded_items.append(
            {
                "componentId": component_id,
                "componentType": component.get("component"),
                "rect": rounded_rect(layout.rect_by_id[component_id]),
                "width": round(width, 2),
                "height": round(height, 2),
                "rootContentWidth": round(root_content_width, 2),
                "rootContentHeight": round(root_content_height, 2),
                "flushEdges": flush_edges,
                "contentClearance": {
                    edge: round(value, 2)
                    for edge, value in content_clearances.items()
                },
                "actionLike": is_action_container(component),
                "paintModel": contact_issue["paintModel"],
                "contactReason": contact_issue["reason"],
                "supportingPeerIds": contact_issue["supportingPeerIds"],
                "borderRadius": component_radius,
                "widthSource": width_source,
                "heightSource": height_source,
            }
        )

    if not crowded_items:
        return []
    return [
        diagnostic(
            "warning",
            "AESTHETIC_ROUNDED_SURFACE_EDGE_SAFE_AREA_LOW",
            "自绘圆角表面贴住父卡片内容盒边界，视觉有效留白为 0vp。",
            json_pointer="/updateComponents/components",
            actual={
                "rootId": context.root_id,
                "rootRadius": root_radius,
                "rootContentWidth": round(root_content_width, 2),
                "rootContentHeight": round(root_content_height, 2),
                "fillTolerance": ROOT_ACTION_CONTENT_FILL_EPSILON_VP,
                "crowdedItems": crowded_items,
                "unresolvedLayoutReasons": layout.unresolved_reasons[:10],
            },
            expected={
                "rootContentEdgeContact": (
                    "自绘动作表面不要横向贴满内容盒；"
                    "右侧自绘表面应避免整列或组合贴住 right+top/bottom"
                )
            },
            fix_hint="缩窄贴边表面，增加父卡片内容区留白，或让右侧角落组件避开内容盒边界。",
        )
    ]


def evaluate_rounded_surface_pair_gap(
    context: AestheticContext,
) -> list[dict[str, Any]]:
    layout = estimate_static_layout(context)
    if layout is None:
        return []
    candidates: list[tuple[str, dict[str, Any], tuple[float, float, float, float]]] = []
    for component in context.components:
        component_id = component.get("id")
        if (
            not isinstance(component_id, str)
            or component_id not in layout.rect_by_id
            or not rounded_visual_surface_candidate(component)
            or not is_effectively_visible(
                component_id, context.components_by_id, context.parent_by_child
            )
        ):
            continue
        rect = layout.rect_by_id[component_id]
        if min(rect[2], rect[3]) + 1e-9 < 24.0:
            continue
        candidates.append((component_id, component, rect))

    crowded_pairs: list[dict[str, Any]] = []
    for first_index, (first_id, first, first_rect) in enumerate(candidates):
        for second_id, second, second_rect in candidates[first_index + 1 :]:
            if first_id == context.root_id or second_id == context.root_id:
                continue
            if is_ancestor_component(first_id, second_id, context) or is_ancestor_component(
                second_id, first_id, context
            ):
                continue
            if context.parent_by_child.get(first_id) == context.parent_by_child.get(
                second_id
            ):
                continue
            gap = rounded_surface_pair_gap(first_rect, second_rect)
            if (
                gap is None
                or float(gap["gap"]) > ROUNDED_SURFACE_PAIR_GAP_VP + 1e-9
            ):
                continue
            crowded_pairs.append(
                {
                    "firstId": first_id,
                    "secondId": second_id,
                    "firstType": first.get("component"),
                    "secondType": second.get("component"),
                    "axis": gap["axis"],
                    "gap": round(gap["gap"], 2),
                    "overlap": round(gap["overlap"], 2),
                    "firstRect": rounded_rect(first_rect),
                    "secondRect": rounded_rect(second_rect),
                }
            )

    if not crowded_pairs:
        return []
    return [
        diagnostic(
            "warning",
            "AESTHETIC_ROUNDED_SURFACE_PAIR_GAP_LOW",
            "不同圆角表面或按钮的静态布局盒已经相接或重叠，视觉上会黏连。",
            json_pointer="/updateComponents/components",
            actual={
                "minimumGap": min(pair["gap"] for pair in crowded_pairs),
                "touchTolerance": ROUNDED_SURFACE_PAIR_GAP_VP,
                "crowdedPairs": crowded_pairs[:30],
                "pairCount": len(crowded_pairs),
                "estimatedTextHeightComponentIds": estimated_text_height_ids(layout),
            },
            expected={
                "roundedSurfaceGap": (
                    f"> {ROUNDED_SURFACE_PAIR_GAP_VP:g}vp; "
                    "only static touch/overlap is reported"
                )
            },
            fix_hint="增加两个圆角面板/按钮之间的行列间距，或收窄其中一个表面。",
        )
    ]


def evaluate_estimated_text_surface_overlap(
    context: AestheticContext,
) -> list[dict[str, Any]]:
    layout = estimate_static_layout(context)
    if layout is None:
        return []
    text_items: list[tuple[str, tuple[float, float, float, float], str]] = []
    targets: list[tuple[str, dict[str, Any], tuple[float, float, float, float]]] = []
    for component in context.components:
        component_id = component.get("id")
        if (
            not isinstance(component_id, str)
            or component_id not in layout.rect_by_id
            or not is_effectively_visible(
                component_id, context.components_by_id, context.parent_by_child
            )
        ):
            continue
        width_source, height_source = layout.dimension_source_by_id.get(
            component_id, ("unknown", "unknown")
        )
        if component.get("component") == "Text" and height_source.startswith(
            "estimated_text"
        ):
            text_items.append((component_id, layout.rect_by_id[component_id], height_source))
        elif surface_or_boundary_target(component):
            targets.append((component_id, component, layout.rect_by_id[component_id]))

    collisions: list[dict[str, Any]] = []
    for text_id, text_rect, height_source in text_items:
        for target_id, target, target_rect in targets:
            if text_id == target_id:
                continue
            if is_ancestor_component(text_id, target_id, context) or is_ancestor_component(
                target_id, text_id, context
            ):
                continue
            relation = text_surface_relation(text_rect, target_rect)
            if relation is None:
                continue
            collisions.append(
                {
                    "textId": text_id,
                    "targetId": target_id,
                    "targetType": target.get("component"),
                    "relation": relation["relation"],
                    "verticalGap": round(relation["verticalGap"], 2),
                    "horizontalOverlap": round(relation["horizontalOverlap"], 2),
                    "intersection": {
                        "width": round(relation["intersectionWidth"], 2),
                        "height": round(relation["intersectionHeight"], 2),
                    },
                    "textRect": rounded_rect(text_rect),
                    "targetRect": rounded_rect(target_rect),
                    "heightSource": height_source,
                }
            )

    if not collisions:
        return []
    return [
        diagnostic(
            "warning",
            "AESTHETIC_ESTIMATED_TEXT_SURFACE_OVERLAP",
            "缺少显式高度的文字按字号估算后压住下方表面、分隔线或边框。",
            json_pointer="/updateComponents/components",
            actual={
                "collisions": collisions[:30],
                "collisionCount": len(collisions),
                "lineHeightRatio": ESTIMATED_TEXT_LINE_HEIGHT_RATIO,
                "minimumGap": ESTIMATED_TEXT_SURFACE_GAP_VP,
            },
            expected="估算文字绘制区与相邻表面、分隔线或边框保持可辨间距。",
            fix_hint="为文字声明足够 height，减少同列内容高度，或增加文字与下方表面/分隔线之间的间距。",
        )
    ]


def rounded_visual_surface_candidate(component: dict[str, Any]) -> bool:
    styles = component.get("styles")
    if not isinstance(styles, dict):
        return False
    if component.get("component") not in {"Button", "Column", "Row", "Stack", "Text"}:
        return False
    radius = numeric(styles.get("borderRadius"))
    if radius is None or radius < 12.0:
        return False
    return component.get("component") == "Button" or any(
        field in styles
        for field in ("backgroundColor", "linearGradient", "borderColor", "borderWidth")
    )


def surface_or_boundary_target(component: dict[str, Any]) -> bool:
    return rounded_visual_surface_candidate(component) or component.get(
        "component"
    ) == "Divider"


def self_drawn_visual_surface(component: dict[str, Any]) -> bool:
    styles = component.get("styles")
    if not isinstance(styles, dict):
        return False
    if component.get("component") not in {"Row", "Column", "Stack", "Text"}:
        return False
    radius = numeric(styles.get("borderRadius"))
    if radius is None or radius < 12.0:
        return False
    return any(
        field in styles
        for field in ("backgroundColor", "linearGradient", "borderColor", "borderWidth")
    )


def visual_surface_paint_model(component: dict[str, Any]) -> str:
    if component.get("component") == "Button":
        return "native_button_layout_box_not_visible_paint_box"
    if self_drawn_visual_surface(component):
        return "self_drawn_surface_layout_box"
    return "unknown"


def root_content_edge_contact_issue(
    component_id: str,
    component: dict[str, Any],
    width: float,
    height: float,
    root_content_width: float,
    root_content_height: float,
    flush_edges: list[str],
    context: AestheticContext,
    layout: StaticLayoutEstimate,
    root_content_rect: tuple[float, float, float, float],
) -> dict[str, Any] | None:
    full_width = "left" in flush_edges and "right" in flush_edges
    right_corner = "right" in flush_edges and (
        "top" in flush_edges or "bottom" in flush_edges
    )
    action_like = is_action_container(component)
    self_drawn = self_drawn_visual_surface(component)
    paint_model = visual_surface_paint_model(component)
    narrow_in_root = width + 1e-9 < root_content_width * 0.75
    right_rail = (
        narrow_in_root
        and "top" in flush_edges
        and "right" in flush_edges
        and "bottom" in flush_edges
        and height + 1e-9 >= root_content_height * 0.8
    )
    peer_ids = right_corner_peer_surface_ids(
        component_id, context, layout, root_content_rect
    )
    if full_width and action_like and self_drawn:
        return {
            "reason": "self_drawn_full_width_action",
            "paintModel": paint_model,
            "supportingPeerIds": [],
        }
    if right_corner and self_drawn and right_rail:
        return {
            "reason": "self_drawn_right_rail",
            "paintModel": paint_model,
            "supportingPeerIds": [],
        }
    if right_corner and narrow_in_root and self_drawn and peer_ids:
        return {
            "reason": "self_drawn_right_column_combo",
            "paintModel": paint_model,
            "supportingPeerIds": peer_ids,
        }
    return None


def right_corner_peer_surface_ids(
    component_id: str,
    context: AestheticContext,
    layout: StaticLayoutEstimate,
    root_content_rect: tuple[float, float, float, float],
) -> list[str]:
    parent_id = context.parent_by_child.get(component_id)
    if parent_id is None:
        return []
    root_content_x, root_content_y, root_content_width, root_content_height = (
        root_content_rect
    )
    peer_ids: list[str] = []
    for sibling_id in child_component_ids(context.components_by_id.get(parent_id, {})):
        if sibling_id == component_id or sibling_id not in layout.rect_by_id:
            continue
        sibling = context.components_by_id.get(sibling_id, {})
        if (
            not rounded_visual_surface_candidate(sibling)
            or not is_effectively_visible(
                sibling_id, context.components_by_id, context.parent_by_child
            )
        ):
            continue
        if not (
            self_drawn_visual_surface(sibling)
            or sibling.get("component") == "Button"
            or is_action_container(sibling)
        ):
            continue
        x, y, width, height = layout.rect_by_id[sibling_id]
        if width + 1e-9 >= root_content_width * 0.75:
            continue
        right = root_content_x + root_content_width - x - width
        top = y - root_content_y
        bottom = root_content_y + root_content_height - y - height
        if abs(right) <= ROOT_ACTION_CONTENT_FILL_EPSILON_VP and (
            abs(top) <= ROOT_ACTION_CONTENT_FILL_EPSILON_VP
            or abs(bottom) <= ROOT_ACTION_CONTENT_FILL_EPSILON_VP
        ):
            peer_ids.append(sibling_id)
    return peer_ids


def rounded_rect(rect: tuple[float, float, float, float]) -> dict[str, float]:
    x, y, width, height = rect
    return {
        "x": round(x, 2),
        "y": round(y, 2),
        "width": round(width, 2),
        "height": round(height, 2),
    }


def estimated_text_height_ids(layout: StaticLayoutEstimate) -> list[str]:
    return [
        component_id
        for component_id, (_, height_source) in layout.dimension_source_by_id.items()
        if height_source.startswith("estimated_text")
    ]


def is_ancestor_component(
    ancestor_id: str, descendant_id: str, context: AestheticContext
) -> bool:
    current_id = context.parent_by_child.get(descendant_id)
    while current_id:
        if current_id == ancestor_id:
            return True
        current_id = context.parent_by_child.get(current_id)
    return False


def rounded_surface_pair_gap(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> dict[str, float | str] | None:
    horizontal_overlap = min(first[0] + first[2], second[0] + second[2]) - max(
        first[0], second[0]
    )
    vertical_overlap = min(first[1] + first[3], second[1] + second[3]) - max(
        first[1], second[1]
    )
    if vertical_overlap > 0.5:
        if first[0] + first[2] <= second[0]:
            gap = second[0] - first[0] - first[2]
        elif second[0] + second[2] <= first[0]:
            gap = first[0] - second[0] - second[2]
        else:
            gap = 0.0
        return {"axis": "horizontal", "gap": gap, "overlap": vertical_overlap}
    if horizontal_overlap > 0.5:
        if first[1] + first[3] <= second[1]:
            gap = second[1] - first[1] - first[3]
        elif second[1] + second[3] <= first[1]:
            gap = first[1] - second[1] - second[3]
        else:
            gap = 0.0
        return {"axis": "vertical", "gap": gap, "overlap": horizontal_overlap}
    return None


def text_surface_relation(
    text_rect: tuple[float, float, float, float],
    target_rect: tuple[float, float, float, float],
) -> dict[str, float | str] | None:
    horizontal_overlap = min(
        text_rect[0] + text_rect[2], target_rect[0] + target_rect[2]
    ) - max(text_rect[0], target_rect[0])
    if horizontal_overlap <= 0.5:
        return None
    intersection = rectangle_intersection(text_rect, target_rect)
    if intersection is not None:
        return {
            "relation": "overlap",
            "verticalGap": -intersection[1],
            "horizontalOverlap": horizontal_overlap,
            "intersectionWidth": intersection[0],
            "intersectionHeight": intersection[1],
        }
    text_bottom = text_rect[1] + text_rect[3]
    target_top = target_rect[1]
    vertical_gap = target_top - text_bottom
    if 0 <= vertical_gap < ESTIMATED_TEXT_SURFACE_GAP_VP:
        return {
            "relation": "low_gap",
            "verticalGap": vertical_gap,
            "horizontalOverlap": horizontal_overlap,
            "intersectionWidth": 0.0,
            "intersectionHeight": 0.0,
        }
    return None


def evaluate_action_surface_edge_clearance(
    context: AestheticContext,
) -> list[dict[str, Any]]:
    """Check action groups that consume the full width of a rounded surface.

    The rule does not guess absolute child positions. It only emits when the
    parent has explicit padding, the action branch has a fixed width equal to
    the complete inner width, and the static side clearance is below a narrow
    safety threshold.
    """

    diagnostics: list[dict[str, Any]] = []
    for container in context.components:
        container_id = container.get("id")
        styles = container.get("styles")
        if (
            container.get("component") not in {"Row", "Column", "Stack"}
            or not isinstance(container_id, str)
            or container_id == context.root_id
            or not isinstance(styles, dict)
            or "padding" not in styles
            or not any(
                field in styles
                for field in ("backgroundColor", "linearGradient", "borderColor")
            )
            or numeric(styles.get("borderRadius")) is None
            or not is_effectively_visible(
                container_id, context.components_by_id, context.parent_by_child
            )
        ):
            continue
        width = static_component_dimension(container, "width", context)
        padding = spacing_sides(styles.get("padding"))
        if width is None or padding is None:
            continue
        _, right, _, left = padding
        inner_width = width - left - right
        if inner_width <= 0:
            continue
        action_branches: list[str] = []
        for child_id in child_component_ids(container):
            child = context.components_by_id.get(child_id, {})
            child_width = static_component_dimension(child, "width", context)
            if (
                child_width is None
                or child_width + 0.5 < inner_width
                or not subtree_contains_action(child_id, context, set())
            ):
                continue
            action_branches.append(child_id)
        if not action_branches:
            continue
        clearance = min(left, right)
        minimum = 4.0
        if clearance + 1e-9 >= minimum:
            continue
        diagnostics.append(
            diagnostic(
                "warning",
                "AESTHETIC_LAYOUT_EDGE_CLEARANCE_LOW",
                "操作区域几乎占满圆角表面，按钮外框与父容器边缘留白不足。",
                json_pointer=(
                    "/updateComponents/components/"
                    f"{context.source_index_by_id[container_id]}/styles/padding"
                ),
                actual={
                    "containerId": container_id,
                    "actionBranchIds": action_branches,
                    "containerWidth": width,
                    "innerWidth": inner_width,
                    "leftClearance": left,
                    "rightClearance": right,
                    "horizontalClearance": clearance,
                },
                expected={"minimumHorizontalClearance": minimum},
                fix_hint="增加父面板左右 padding，或缩窄按钮外框，让操作区与圆角边缘保留明确呼吸空间。",
            )
        )

    root = context.components_by_id.get(context.root_id or "", {})
    root_styles = root.get("styles") if isinstance(root, dict) else None
    root_radius = (
        numeric(root_styles.get("borderRadius"))
        if isinstance(root_styles, dict)
        else None
    )
    root_padding = (
        spacing_sides(root_styles.get("padding"))
        if isinstance(root_styles, dict)
        else None
    )
    if (
        isinstance(root_styles, dict)
        and root.get("component") in {"Row", "Column"}
        and root_radius is not None
        and root_radius >= 16.0
        and root_padding is not None
        and is_effectively_visible(
            context.root_id or "", context.components_by_id, context.parent_by_child
        )
    ):
        _, right, bottom, _ = root_padding
        corner_actions = statically_flush_corner_actions(
            context.root_id or "", context, "bottomRight", set()
        )
        crowded_actions: list[str] = []
        minimums: list[float] = []
        for action_id in corner_actions:
            action = context.components_by_id.get(action_id, {})
            action_styles = action.get("styles") if isinstance(action, dict) else None
            if not isinstance(action_styles, dict):
                continue
            action_radius = numeric(action_styles.get("borderRadius"))
            action_height = numeric(action_styles.get("height"))
            if action_radius is None or action_height is None:
                continue
            minimum = min(8.0, root_radius, action_radius, action_height / 2.0)
            if min(right, bottom) + 1e-9 >= minimum:
                continue
            crowded_actions.append(action_id)
            minimums.append(minimum)
        if crowded_actions:
            minimum = max(minimums)
            diagnostics.append(
                diagnostic(
                    "warning",
                    "AESTHETIC_LAYOUT_EDGE_CLEARANCE_LOW",
                    "操作控件占据圆角卡片角落，控件与外框圆角的安全留白不足。",
                    json_pointer=(
                        "/updateComponents/components/"
                        f"{context.source_index_by_id[context.root_id or '']}/styles/padding"
                    ),
                    actual={
                        "containerId": context.root_id,
                        "actionIds": crowded_actions,
                        "corner": "bottomRight",
                        "rightClearance": right,
                        "bottomClearance": bottom,
                        "cornerClearance": min(right, bottom),
                        "containerRadius": root_radius,
                    },
                    expected={"minimumCornerClearance": minimum},
                    fix_hint="增加卡片右侧和底部 padding，或缩小角落按钮，使按钮避开外框圆角的视觉拥挤区。",
                )
            )
    return diagnostics


def evaluate_surface_content_edge_clearance(
    context: AestheticContext,
) -> list[dict[str, Any]]:
    """Check provable horizontal crowding inside rounded DSL surfaces.

    The runtime accepts scalar spacing or a named-edge object. Array shorthand
    is ignored by ``StyleMapper.mapEdgeValue`` and therefore contributes zero
    padding. To stay conservative, ordinary zero-padding surfaces are only
    reported when a direct action consumes the complete inner width; array
    shorthand is reported because its declared clearance is provably absent at
    render time.
    """

    diagnostics: list[dict[str, Any]] = []
    minimum = 4.0
    surface_fields = {
        "backgroundColor", "linearGradient", "borderColor", "borderWidth"
    }

    for container in context.components:
        container_id = container.get("id")
        styles = container.get("styles")
        if (
            container.get("component") not in {"Column", "Row"}
            or not isinstance(container_id, str)
            or container_id == context.root_id
            or not isinstance(styles, dict)
            or numeric(styles.get("borderRadius")) is None
            or not any(field in styles for field in surface_fields)
            or not is_effectively_visible(
                container_id, context.components_by_id, context.parent_by_child
            )
        ):
            continue
        width = static_component_dimension(container, "width", context)
        padding = spacing_sides(styles.get("padding"))
        if width is None or padding is None:
            continue
        _, right_padding, _, left_padding = padding
        inner_width = width - left_padding - right_padding
        if inner_width <= 0:
            continue
        runtime_collapsed_padding = edge_value_collapses_to_zero(
            styles.get("padding")
        )
        align = styles.get("alignItems", "start")
        horizontal_positions: dict[str, tuple[float, float]] = {}
        if container.get("component") == "Row":
            if styles.get("justifyContent", "start") not in {
                "start", "flex-start"
            }:
                continue
            row_gap = numeric(container.get("itemMargin", 0))
            if row_gap is None:
                continue
            cursor = left_padding
            positions_resolved = True
            for row_child_id in child_component_ids(container):
                row_child = context.components_by_id.get(row_child_id, {})
                row_child_styles = row_child.get("styles")
                row_child_width = static_component_dimension(
                    row_child, "width", context
                )
                row_child_margins = spacing_sides(
                    row_child_styles.get("margin")
                    if isinstance(row_child_styles, dict)
                    else None
                )
                if row_child_width is None or row_child_margins is None:
                    positions_resolved = False
                    break
                _, row_child_right, _, row_child_left = row_child_margins
                child_start = cursor + row_child_left
                horizontal_positions[row_child_id] = (
                    child_start,
                    width - child_start - row_child_width,
                )
                cursor += (
                    row_child_left + row_child_width + row_child_right + row_gap
                )
            if not positions_resolved:
                continue
        crowded_items: list[dict[str, Any]] = []
        for child_id in child_component_ids(container):
            child = context.components_by_id.get(child_id, {})
            child_styles = child.get("styles")
            child_type = child.get("component")
            if (
                child_type not in {"Text", "Button"}
                or not isinstance(child_styles, dict)
                or not is_effectively_visible(
                    child_id, context.components_by_id, context.parent_by_child
                )
            ):
                continue
            child_width = static_component_dimension(child, "width", context)
            margins = spacing_sides(child_styles.get("margin"))
            if child_width is None or margins is None:
                continue
            _, child_right, _, child_left = margins
            occupied_width = child_left + child_width + child_right
            if container.get("component") == "Row":
                position = horizontal_positions.get(child_id)
                if position is None:
                    continue
                left_clearance, right_clearance = position
            elif align in {"center"}:
                free = inner_width - occupied_width
                left_clearance = left_padding + free / 2.0 + child_left
                right_clearance = right_padding + free / 2.0 + child_right
            elif align in {"end", "flex-end"}:
                left_clearance = width - right_padding - occupied_width + child_left
                right_clearance = right_padding + child_right
            elif align in {"start", "flex-start", None}:
                left_clearance = left_padding + child_left
                right_clearance = width - left_clearance - child_width
            else:
                continue
            clearance = min(left_clearance, right_clearance)
            fills_action_surface = (
                child_type == "Button"
                and occupied_width + 0.5 >= inner_width
            )
            if (
                clearance + 1e-9 >= minimum
                or not (runtime_collapsed_padding or fills_action_surface)
            ):
                continue
            crowded_items.append(
                {
                    "componentId": child_id,
                    "componentType": child_type,
                    "leftClearance": round(left_clearance, 2),
                    "rightClearance": round(right_clearance, 2),
                    "minimumClearance": round(clearance, 2),
                }
            )
        if crowded_items:
            diagnostics.append(
                diagnostic(
                    "warning",
                    "AESTHETIC_SURFACE_CONTENT_EDGE_CLEARANCE_LOW",
                    "圆角表面内的文字或控件缺少可辨的水平边缘留白。",
                    json_pointer=(
                        "/updateComponents/components/"
                        f"{context.source_index_by_id[container_id]}/styles"
                    ),
                    actual={
                        "containerId": container_id,
                        "declaredPadding": styles.get("padding"),
                        "runtimePadding": {
                            "top": padding[0], "right": padding[1],
                            "bottom": padding[2], "left": padding[3],
                        },
                        "unsupportedArrayPadding": isinstance(
                            styles.get("padding"), list
                        ),
                        "runtimeCollapsedPadding": runtime_collapsed_padding,
                        "minimumHorizontalClearance": min(
                            item["minimumClearance"] for item in crowded_items
                        ),
                        "crowdedItems": crowded_items,
                    },
                    expected={"minimumHorizontalClearance": minimum},
                    fix_hint="将 padding 改为数值或命名边对象，并让文字、按钮与圆角边缘至少保留 4vp。",
                )
            )

    for component in context.components:
        component_id = component.get("id")
        styles = component.get("styles")
        if (
            component.get("component") != "Text"
            or not isinstance(component_id, str)
            or not isinstance(styles, dict)
            or not edge_value_collapses_to_zero(styles.get("padding"))
            or numeric(styles.get("borderRadius")) is None
            or not any(field in styles for field in surface_fields)
            or styles.get("textAlign", "start")
            not in {"start", "left", "end", "right"}
            or resolve_visible_text(component, context) is None
            or not is_effectively_visible(
                component_id, context.components_by_id, context.parent_by_child
            )
        ):
            continue
        padding = spacing_sides(styles.get("padding"))
        if padding is None:
            continue
        alignment = styles.get("textAlign", "start")
        clearance = padding[1] if alignment in {"end", "right"} else padding[3]
        if clearance + 1e-9 >= minimum:
            continue
        diagnostics.append(
            diagnostic(
                "warning",
                "AESTHETIC_SURFACE_CONTENT_EDGE_CLEARANCE_LOW",
                "文字自身的圆角表面未获得运行时水平内边距。",
                json_pointer=(
                    "/updateComponents/components/"
                    f"{context.source_index_by_id[component_id]}/styles/padding"
                ),
                actual={
                    "componentId": component_id,
                    "declaredPadding": styles.get("padding"),
                    "runtimePadding": {
                        "top": padding[0], "right": padding[1],
                        "bottom": padding[2], "left": padding[3],
                    },
                    "unsupportedArrayPadding": True,
                    "minimumHorizontalClearance": clearance,
                },
                expected={"minimumHorizontalClearance": minimum},
                fix_hint="将数组 padding 改成命名边对象，使圆角标签内的文字获得真实左右留白。",
            )
        )
    return diagnostics


def assess_rounded_surface_content_clearance(
    context: AestheticContext,
    diagnostics: list[dict[str, Any]],
) -> dict[str, Any]:
    surface_fields = {
        "backgroundColor", "linearGradient", "borderColor", "borderWidth"
    }
    candidate_ids: list[str] = []
    unresolved_reasons: list[str] = []
    for component in context.components:
        component_id = component.get("id")
        component_type = component.get("component")
        styles = component.get("styles")
        if (
            not isinstance(component_id, str)
            or not isinstance(styles, dict)
            or "borderRadius" not in styles
            or not any(field in styles for field in surface_fields)
            or not is_effectively_visible(
                component_id, context.components_by_id, context.parent_by_child
            )
        ):
            continue
        direct_content_ids = [
            child_id
            for child_id in child_component_ids(component)
            if context.components_by_id.get(child_id, {}).get("component")
            in {"Text", "Button"}
            and is_effectively_visible(
                child_id, context.components_by_id, context.parent_by_child
            )
        ]
        is_text_surface = (
            component_type == "Text"
            and resolve_visible_text(component, context) is not None
        )
        if component_type not in {"Column", "Row"} and not is_text_surface:
            continue
        if not direct_content_ids and not is_text_surface:
            continue
        candidate_ids.append(component_id)
        if numeric(styles.get("borderRadius")) is None:
            unresolved_reasons.append(
                f"{component_id}: borderRadius 无法静态求解"
            )
        if spacing_sides(styles.get("padding")) is None:
            unresolved_reasons.append(
                f"{component_id}: padding 无法静态求解"
            )
        if component_type in {"Column", "Row"}:
            if static_component_dimension(component, "width", context) is None:
                unresolved_reasons.append(
                    f"{component_id}: 表面宽度无法静态求解"
                )
            if component_type == "Column" and styles.get(
                "alignItems", "start"
            ) not in {"start", "flex-start", "center", "end", "flex-end", None}:
                unresolved_reasons.append(
                    f"{component_id}: alignItems 无法静态求解"
                )
            if component_type == "Row" and styles.get(
                "justifyContent", "start"
            ) not in {"start", "flex-start", "center"}:
                unresolved_reasons.append(
                    f"{component_id}: Row justifyContent 尚未建模"
                )
            for child_id in child_component_ids(component):
                child = context.components_by_id.get(child_id, {})
                child_styles = child.get("styles")
                if (
                    static_component_dimension(child, "width", context) is None
                    or spacing_sides(
                        child_styles.get("margin")
                        if isinstance(child_styles, dict)
                        else None
                    )
                    is None
                ):
                    unresolved_reasons.append(
                        f"{component_id}/{child_id}: 子项宽度或 margin 无法静态求解"
                    )
                    break
        elif styles.get("textAlign", "start") not in {
            "start", "left", "center", "end", "right"
        }:
            unresolved_reasons.append(
                f"{component_id}: textAlign 无法静态求解"
            )

    if diagnostics:
        return rule_assessment(
            "rounded_surface_content_clearance",
            "issue",
            "proven_static_geometry",
            component_ids=candidate_ids,
            reasons=unresolved_reasons,
        )
    if not candidate_ids:
        return rule_assessment(
            "rounded_surface_content_clearance",
            "not_applicable",
            "structural",
        )
    if unresolved_reasons:
        return rule_assessment(
            "rounded_surface_content_clearance",
            "undetermined",
            "unknown_geometry",
            component_ids=candidate_ids,
            reasons=unresolved_reasons,
        )
    return rule_assessment(
        "rounded_surface_content_clearance",
        "clear",
        "proven_static_geometry",
        component_ids=candidate_ids,
    )


def evaluate_stack_text_image_overlap(
    context: AestheticContext,
) -> list[dict[str, Any]]:
    """Report text/image intersections only for fully static Stack geometry."""

    diagnostics: list[dict[str, Any]] = []
    for container in context.components:
        container_id = container.get("id")
        styles = container.get("styles")
        if (
            container.get("component") != "Stack"
            or not isinstance(container_id, str)
            or not isinstance(styles, dict)
            or not is_effectively_visible(
                container_id, context.components_by_id, context.parent_by_child
            )
        ):
            continue
        width = static_component_dimension(container, "width", context)
        height = static_component_dimension(container, "height", context)
        padding = spacing_sides(styles.get("padding"))
        if width is None or height is None or padding is None:
            continue
        top, right, bottom, left = padding
        inner = (left, top, width - left - right, height - top - bottom)
        if inner[2] <= 0 or inner[3] <= 0:
            continue
        alignment = styles.get("alignContent", "center")
        branch_leaves: list[dict[str, Any]] = []
        resolved = True
        for branch_id in child_component_ids(container):
            child = context.components_by_id.get(branch_id, {})
            child_width = static_component_dimension(child, "width", context)
            child_height = static_component_dimension(child, "height", context)
            child_styles = child.get("styles")
            margins = spacing_sides(
                child_styles.get("margin") if isinstance(child_styles, dict) else None
            )
            if child_width is None or child_height is None or margins is None:
                resolved = False
                break
            child_rect = static_stack_child_rect(
                inner, child_width, child_height, margins, alignment
            )
            if child_rect is None:
                resolved = False
                break
            leaves = collect_static_overlap_leaves(
                branch_id, child_rect, branch_id, context, set()
            )
            if leaves is None:
                resolved = False
                break
            branch_leaves.extend(leaves)
        if not resolved:
            continue
        images = [item for item in branch_leaves if item["kind"] == "image"]
        texts = [item for item in branch_leaves if item["kind"] == "text"]
        overlapping_pairs: list[dict[str, Any]] = []
        for image in images:
            for text_item in texts:
                if image["branchId"] == text_item["branchId"]:
                    continue
                if text_item.get("surfaceBlocksLowerImage") and (
                    stack_branch_index(container, image["branchId"])
                    < stack_branch_index(container, text_item["branchId"])
                ):
                    continue
                if not stack_image_branch_reaches_text_branch(
                    container,
                    image["branchId"],
                    text_item["branchId"],
                    context,
                ):
                    continue
                intersection = rectangle_intersection(image["rect"], text_item["rect"])
                if intersection is None:
                    continue
                overlapping_pairs.append(
                    {
                        "imageId": image["componentId"],
                        "textId": text_item["componentId"],
                        "imageBranchId": image["branchId"],
                        "textBranchId": text_item["branchId"],
                        "intersectionWidth": round(intersection[0], 2),
                        "intersectionHeight": round(intersection[1], 2),
                    }
                )
        if not overlapping_pairs:
            continue
        diagnostics.append(
            diagnostic(
                "warning",
                "AESTHETIC_STACK_TEXT_IMAGE_OVERLAP",
                "固定尺寸 Stack 中的文字框与图片框发生可证明的矩形相交。",
                json_pointer=(
                    "/updateComponents/components/"
                    f"{context.source_index_by_id[container_id]}"
                ),
                actual={
                    "containerId": container_id,
                    "overlappingPairs": overlapping_pairs,
                },
                expected="不同 Stack 分支的可见文字框与图片框不应相交。",
                fix_hint="重新分区或缩小图片/文字区域，确保文字与图片在静态布局中不发生矩形相交。",
            )
        )
    return diagnostics


def assess_stack_text_image_overlap(
    context: AestheticContext,
    diagnostics: list[dict[str, Any]],
) -> dict[str, Any]:
    """Classify Stack overlap without collapsing unknown geometry into clear."""

    candidate_ids: list[str] = []
    unresolved_reasons: list[str] = []
    for container in context.components:
        container_id = container.get("id")
        styles = container.get("styles")
        if (
            container.get("component") != "Stack"
            or not isinstance(container_id, str)
            or not isinstance(styles, dict)
            or not is_effectively_visible(
                container_id, context.components_by_id, context.parent_by_child
            )
        ):
            continue
        branches = child_component_ids(container)
        image_branches = {
            branch_id
            for branch_id in branches
            if subtree_has_visible_type(branch_id, "Image", context, set())
        }
        text_branches = {
            branch_id
            for branch_id in branches
            if subtree_has_visible_or_unresolved_text(branch_id, context, set())
        }
        if not any(
            image_branch != text_branch
            and stack_image_branch_reaches_text_branch(
                container, image_branch, text_branch, context
            )
            for image_branch in image_branches
            for text_branch in text_branches
        ):
            continue
        candidate_ids.append(container_id)
        width = static_component_dimension(container, "width", context)
        height = static_component_dimension(container, "height", context)
        padding = spacing_sides(styles.get("padding"))
        if width is None or height is None or padding is None:
            unresolved_reasons.append(
                f"{container_id}: Stack width/height/padding 无法静态求解"
            )
            continue
        top, right, bottom, left = padding
        inner = (left, top, width - left - right, height - top - bottom)
        alignment = styles.get("alignContent", "center")
        if inner[2] <= 0 or inner[3] <= 0:
            unresolved_reasons.append(f"{container_id}: Stack 内容框无效")
            continue
        for branch_id in branches:
            child = context.components_by_id.get(branch_id, {})
            child_styles = child.get("styles")
            child_width = static_component_dimension(child, "width", context)
            child_height = static_component_dimension(child, "height", context)
            margins = spacing_sides(
                child_styles.get("margin")
                if isinstance(child_styles, dict)
                else None
            )
            if child_width is None or child_height is None or margins is None:
                unresolved_reasons.append(
                    f"{container_id}/{branch_id}: 分支 width/height/margin 无法静态求解"
                )
                break
            child_rect = static_stack_child_rect(
                inner, child_width, child_height, margins, alignment
            )
            if child_rect is None:
                unresolved_reasons.append(
                    f"{container_id}: alignContent={alignment!r} 不受静态求解器支持"
                )
                break
            if collect_static_overlap_leaves(
                branch_id, child_rect, branch_id, context, set()
            ) is None:
                unresolved_reasons.append(
                    f"{container_id}/{branch_id}: 分支布局无法静态闭合"
                )
                break

    if diagnostics:
        return rule_assessment(
            "stack_text_image_overlap",
            "issue",
            "proven_static_geometry",
            component_ids=candidate_ids,
        )
    if not candidate_ids:
        return rule_assessment(
            "stack_text_image_overlap",
            "not_applicable",
            "structural",
        )
    if unresolved_reasons:
        return rule_assessment(
            "stack_text_image_overlap",
            "undetermined",
            "unknown_geometry",
            component_ids=candidate_ids,
            reasons=unresolved_reasons,
        )
    return rule_assessment(
        "stack_text_image_overlap",
        "clear",
        "proven_static_geometry",
        component_ids=candidate_ids,
    )


def stack_image_branch_reaches_text_branch(
    stack: dict[str, Any],
    image_branch_id: str,
    text_branch_id: str,
    context: AestheticContext,
) -> bool:
    """Return false only when a full opaque layer provably shields the text.

    Stack children paint in source order.  A solid full-size sibling between a
    lower image branch and a higher text branch blocks the image pixels.  A
    cover below a later image cannot shield the text from that image.
    """

    children = child_component_ids(stack)
    if image_branch_id not in children or text_branch_id not in children:
        return True
    image_index = children.index(image_branch_id)
    text_index = children.index(text_branch_id)
    if image_index >= text_index:
        return True
    return not any(
        proven_full_opaque_solid_cover(
            context.components_by_id.get(sibling_id, {}), stack
        )
        is not None
        for sibling_id in children[image_index + 1 : text_index]
    )


def stack_branch_index(stack: dict[str, Any], branch_id: str) -> int:
    children = child_component_ids(stack)
    return children.index(branch_id) if branch_id in children else -1


def subtree_has_visible_type(
    component_id: str,
    component_type: str,
    context: AestheticContext,
    visited: set[str],
) -> bool:
    if component_id in visited:
        return False
    visited.add(component_id)
    component = context.components_by_id.get(component_id, {})
    if not is_effectively_visible(
        component_id, context.components_by_id, context.parent_by_child
    ):
        return False
    if component.get("component") == component_type:
        if component_type != "Text":
            return True
        text = resolve_visible_text(component, context)
        return isinstance(text, str) and bool(text.strip())
    return any(
        subtree_has_visible_type(child_id, component_type, context, visited.copy())
        for child_id in child_component_ids(component)
    )


def subtree_has_visible_or_unresolved_text(
    component_id: str,
    context: AestheticContext,
    visited: set[str],
) -> bool:
    """Treat unresolved dynamic Text as a candidate, never as absent content."""

    if component_id in visited:
        return False
    visited.add(component_id)
    component = context.components_by_id.get(component_id, {})
    if not is_effectively_visible(
        component_id, context.components_by_id, context.parent_by_child
    ):
        return False
    if component.get("component") == "Text":
        raw_text = visible_text_value(component)
        if raw_text is None:
            return False
        resolved_text = resolve_visible_text(component, context)
        return (
            isinstance(resolved_text, str) and bool(resolved_text.strip())
        ) or (is_dynamic_dsl_value(raw_text) and resolved_text is None)
    return any(
        subtree_has_visible_or_unresolved_text(child_id, context, visited.copy())
        for child_id in child_component_ids(component)
    )


def static_stack_child_rect(
    inner: tuple[float, float, float, float],
    width: float,
    height: float,
    margins: tuple[float, float, float, float],
    alignment: object,
) -> tuple[float, float, float, float] | None:
    top, right, bottom, left = margins
    occupied_width = left + width + right
    occupied_height = top + height + bottom
    x0, y0, inner_width, inner_height = inner
    if alignment == "center":
        x = x0 + (inner_width - occupied_width) / 2.0 + left
        y = y0 + (inner_height - occupied_height) / 2.0 + top
    elif alignment in {"start", "topStart", "topLeft"}:
        x = x0 + left
        y = y0 + top
    elif alignment in {"end", "bottomEnd", "bottomRight"}:
        x = x0 + inner_width - occupied_width + left
        y = y0 + inner_height - occupied_height + top
    else:
        return None
    return x, y, width, height


def collect_static_overlap_leaves(
    component_id: str,
    rect: tuple[float, float, float, float],
    branch_id: str,
    context: AestheticContext,
    visited: set[str],
) -> list[dict[str, Any]] | None:
    if component_id in visited:
        return None
    visited.add(component_id)
    component = context.components_by_id.get(component_id, {})
    if not is_effectively_visible(
        component_id, context.components_by_id, context.parent_by_child
    ):
        return []
    styles = component.get("styles")
    if not isinstance(styles, dict):
        return None
    component_type = component.get("component")
    if component_type == "Image":
        return [{
            "kind": "image", "componentId": component_id,
            "branchId": branch_id, "rect": rect,
        }]
    if component_type == "Text":
        surface_state = text_surface_blocks_image(styles)
        if surface_state is None:
            return None
        raw_text = visible_text_value(component)
        text = resolve_visible_text(component, context)
        if text is None:
            return None if raw_text and is_dynamic_dsl_value(raw_text) else []
        if not text.strip():
            return []
        return [{
            "kind": "text", "componentId": component_id,
            "branchId": branch_id, "rect": rect,
            "surfaceBlocksLowerImage": surface_state,
        }]
    if component_type not in {"Column", "Row"}:
        return None

    padding = spacing_sides(styles.get("padding"))
    if padding is None:
        return None
    top, right, bottom, left = padding
    x0, y0, width, height = rect
    inner = (x0 + left, y0 + top, width - left - right, height - top - bottom)
    if inner[2] <= 0 or inner[3] <= 0:
        return None
    child_specs: list[tuple[str, float, float, tuple[float, float, float, float]]] = []
    for child_id in child_component_ids(component):
        child = context.components_by_id.get(child_id, {})
        child_styles = child.get("styles")
        child_width = static_component_dimension(child, "width", context)
        child_height = static_component_dimension(child, "height", context)
        margins = spacing_sides(
            child_styles.get("margin") if isinstance(child_styles, dict) else None
        )
        if child_width is None or child_height is None or margins is None:
            return None
        child_specs.append((child_id, child_width, child_height, margins))
    if not child_specs:
        return []
    item_margin = numeric(component.get("itemMargin", 0))
    if item_margin is None:
        return None
    is_row = component_type == "Row"
    occupied_main = [
        (
            margins[3] + child_width + margins[1]
            if is_row
            else margins[0] + child_height + margins[2]
        )
        for _, child_width, child_height, margins in child_specs
    ]
    main_origin = inner[0] if is_row else inner[1]
    main_size = inner[2] if is_row else inner[3]
    justify = styles.get("justifyContent", "start")
    if justify in {"start", "flex-start"}:
        gap = item_margin
        cursor = main_origin
    elif justify == "center":
        gap = item_margin
        total = sum(occupied_main) + gap * (len(child_specs) - 1)
        cursor = main_origin + (main_size - total) / 2.0
    elif justify in {"end", "flex-end"}:
        gap = item_margin
        total = sum(occupied_main) + gap * (len(child_specs) - 1)
        cursor = main_origin + main_size - total
    elif justify == "spaceBetween" and len(child_specs) > 1:
        gap = (main_size - sum(occupied_main)) / (len(child_specs) - 1)
        if gap + 1e-9 < item_margin:
            return None
        cursor = main_origin
    else:
        return None
    align = styles.get("alignItems", "start")
    leaves: list[dict[str, Any]] = []
    for child_id, child_width, child_height, margins in child_specs:
        child_top, child_right, child_bottom, child_left = margins
        occupied_width = child_left + child_width + child_right
        occupied_height = child_top + child_height + child_bottom
        if is_row:
            child_x = cursor + child_left
            if align in {"start", "flex-start"}:
                child_y = inner[1] + child_top
            elif align == "center":
                child_y = (
                    inner[1]
                    + (inner[3] - occupied_height) / 2.0
                    + child_top
                )
            elif align in {"end", "flex-end"}:
                child_y = (
                    inner[1] + inner[3] - occupied_height + child_top
                )
            else:
                return None
        else:
            child_y = cursor + child_top
            if align in {"start", "flex-start"}:
                child_x = inner[0] + child_left
            elif align == "center":
                child_x = (
                    inner[0]
                    + (inner[2] - occupied_width) / 2.0
                    + child_left
                )
            elif align in {"end", "flex-end"}:
                child_x = inner[0] + inner[2] - occupied_width + child_left
            else:
                return None
        child_rect = (child_x, child_y, child_width, child_height)
        child_leaves = collect_static_overlap_leaves(
            child_id, child_rect, branch_id, context, visited.copy()
        )
        if child_leaves is None:
            return None
        leaves.extend(child_leaves)
        cursor += (occupied_width if is_row else occupied_height) + gap
    return leaves


def text_surface_blocks_image(styles: dict[str, Any]) -> bool | None:
    """Classify whether a Text background provably hides lower image pixels.

    Border-only and translucent fills do not block the image.  Dynamic or
    image-backed surfaces remain unknown instead of being treated as a cover.
    """

    if "backgroundImage" in styles:
        return None
    if "backgroundColor" in styles:
        color = parse_hex_color(styles.get("backgroundColor"))
        if color is None:
            return None
        return color[3] >= 0.999
    if "linearGradient" in styles:
        colors, _, uncertainty = background_layer(styles)
        if uncertainty or not colors:
            return None
        return all(color[3] >= 0.999 for color in colors)
    return False


def rectangle_intersection(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> tuple[float, float] | None:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[0] + first[2], second[0] + second[2])
    bottom = min(first[1] + first[3], second[1] + second[3])
    if right - left <= 0.5 or bottom - top <= 0.5:
        return None
    return right - left, bottom - top


def statically_flush_corner_actions(
    component_id: str,
    context: AestheticContext,
    corner: str,
    visited: set[str],
) -> list[str]:
    """Return actions provably flush with both content-box edges of a corner."""

    if corner != "bottomRight" or component_id in visited:
        return []
    visited.add(component_id)
    component = context.components_by_id.get(component_id, {})
    if component_id != context.root_id and is_action_container(component):
        return [component_id]
    component_type = component.get("component")
    styles = component.get("styles")
    children = child_component_ids(component)
    if (
        component_type not in {"Row", "Column"}
        or not isinstance(styles, dict)
        or not children
    ):
        return []
    width = static_component_dimension(component, "width", context)
    height = static_component_dimension(component, "height", context)
    padding = spacing_sides(styles.get("padding"))
    if width is None or height is None or padding is None:
        return []
    top, right, bottom, left = padding
    inner_width = width - left - right
    inner_height = height - top - bottom
    if inner_width <= 0 or inner_height <= 0:
        return []

    child_sizes: list[tuple[str, float, float]] = []
    for child_id in children:
        child = context.components_by_id.get(child_id, {})
        child_styles = child.get("styles") if isinstance(child, dict) else None
        if (
            not isinstance(child_styles, dict)
            or any(
                field in child_styles
                for field in ("layoutWeight", "flexShrink", "flexGrow")
            )
            or spacing_sides(child_styles.get("margin"))
            != (0.0, 0.0, 0.0, 0.0)
        ):
            return []
        child_width = static_component_dimension(child, "width", context)
        child_height = static_component_dimension(child, "height", context)
        if child_width is None or child_height is None:
            return []
        child_sizes.append((child_id, child_width, child_height))

    gap = numeric(component.get("itemMargin"))
    if gap is None:
        if "itemMargin" in component:
            return []
        gap = 0.0
    if component_type == "Row":
        required_main = sum(item[1] for item in child_sizes) + gap * (
            len(child_sizes) - 1
        )
        if abs(required_main - inner_width) > 0.5:
            return []
        child_id, _, child_height = child_sizes[-1]
        if abs(child_height - inner_height) > 0.5:
            return []
    else:
        if component_id == context.root_id and styles.get("justifyContent") not in {
            "spaceBetween",
            "end",
            "flex-end",
        }:
            return []
        required_main = sum(item[2] for item in child_sizes) + gap * (
            len(child_sizes) - 1
        )
        if abs(required_main - inner_height) > 0.5:
            return []
        child_id, child_width, _ = child_sizes[-1]
        if abs(child_width - inner_width) > 0.5:
            return []

    return statically_flush_corner_actions(
        child_id, context, corner, visited
    )


def subtree_contains_action(
    component_id: str, context: AestheticContext, visited: set[str]
) -> bool:
    if component_id in visited:
        return False
    visited.add(component_id)
    component = context.components_by_id.get(component_id, {})
    if is_action_container(component):
        return True
    return any(
        subtree_contains_action(child_id, context, visited)
        for child_id in child_component_ids(component)
    )


def spacing_axis_total(value: object, axis: str) -> float | None:
    sides = spacing_sides(value)
    if sides is None:
        return None
    top, right, bottom, left = sides
    return left + right if axis == "width" else top + bottom


def spacing_sides(value: object) -> tuple[float, float, float, float] | None:
    """Return runtime-effective top/right/bottom/left spacing values.

    The current DSL renderer does not implement CSS-style array shorthand.
    Arrays reach ``StyleMapper.mapEdgeValue`` as objects without named edge
    keys, so all four runtime sides resolve to zero.
    """

    if value is None:
        return 0.0, 0.0, 0.0, 0.0
    if isinstance(value, bool):
        return 0.0, 0.0, 0.0, 0.0
    if isinstance(value, (int, float)):
        number = numeric(value)
        if number is None or number < 0:
            return 0.0, 0.0, 0.0, 0.0
        return number, number, number, number
    if isinstance(value, str):
        if is_dynamic_dsl_value(value):
            return None
        return 0.0, 0.0, 0.0, 0.0
    if isinstance(value, list):
        return 0.0, 0.0, 0.0, 0.0
    if not isinstance(value, dict):
        return None
    resolved: list[float] = []
    has_absolute = False
    has_percent = False
    for edge in ("top", "right", "bottom", "left"):
        raw = value.get(edge, 0)
        if is_dynamic_dsl_value(raw):
            return None
        if isinstance(raw, bool):
            resolved.append(0.0)
            continue
        if isinstance(raw, (int, float)):
            number = numeric(raw)
            number = 0.0 if number is None or number < 0 else number
            has_absolute = has_absolute or number != 0
            resolved.append(float(number))
            continue
        if isinstance(raw, str):
            percent = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)%\s*", raw)
            if percent:
                number = float(percent.group(1))
                if number < 0:
                    resolved.append(0.0)
                else:
                    has_percent = has_percent or number != 0
                    resolved.append(number)
                continue
            number = numeric(raw)
            if number is None or number < 0:
                resolved.append(0.0)
            else:
                has_absolute = has_absolute or number != 0
                resolved.append(float(number))
            continue
        resolved.append(0.0)
    if has_absolute and has_percent:
        return 0.0, 0.0, 0.0, 0.0
    if has_percent:
        return None
    return tuple(resolved)  # type: ignore[return-value]


def runtime_spacing_value_state(value: object) -> str:
    """Classify one mapEdgeValue input as mapped, reset, or unresolved."""

    if is_dynamic_dsl_value(value):
        return "unknown"
    if isinstance(value, bool):
        return "reset"
    if isinstance(value, (int, float)):
        number = numeric(value)
        return "mapped" if number is not None and number >= 0 else "reset"
    if isinstance(value, str):
        return "reset"
    if isinstance(value, list):
        return "reset"
    if not isinstance(value, dict):
        return "reset"
    physical = {"top", "right", "bottom", "left"}
    if value and not physical.intersection(value):
        return "reset"
    if any(is_dynamic_dsl_value(value.get(edge)) for edge in physical):
        return "unknown"
    if edge_value_collapses_to_zero(value):
        return "reset"
    for edge in physical:
        raw = value.get(edge)
        if raw is None:
            continue
        if isinstance(raw, bool) or isinstance(raw, (dict, list)):
            return "reset"
        if isinstance(raw, (int, float)):
            number = numeric(raw)
            if number is None or number < 0:
                return "reset"
            continue
        if isinstance(raw, str):
            percent = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)%\s*", raw)
            number = float(percent.group(1)) if percent else numeric(raw)
            if number is None or number < 0:
                return "reset"
            continue
        return "reset"
    return "mapped"


def assess_runtime_spacing_contract(
    context: AestheticContext,
) -> dict[str, Any]:
    candidate_ids: list[str] = []
    reset_reasons: list[str] = []
    unknown_reasons: list[str] = []
    for component in context.components:
        component_id = component.get("id")
        styles = component.get("styles")
        if not isinstance(component_id, str) or not isinstance(styles, dict):
            continue
        for field in ("padding", "margin"):
            if field not in styles:
                continue
            if component_id not in candidate_ids:
                candidate_ids.append(component_id)
            state = runtime_spacing_value_state(styles.get(field))
            if state == "reset":
                reset_reasons.append(
                    f"{component_id}.{field}: mapEdgeValue 将声明值重置"
                )
            elif state == "unknown":
                unknown_reasons.append(
                    f"{component_id}.{field}: 动态值的运行时类型未知"
                )
        if "itemMargin" in component:
            if component_id not in candidate_ids:
                candidate_ids.append(component_id)
            raw_gap = component.get("itemMargin")
            if is_dynamic_dsl_value(raw_gap) or numeric(raw_gap) is None:
                unknown_reasons.append(
                    f"{component_id}.itemMargin: 无法静态求解"
                )
    if not candidate_ids:
        return rule_assessment(
            "runtime_spacing_contract", "not_applicable", "structural"
        )
    if unknown_reasons:
        return rule_assessment(
            "runtime_spacing_contract",
            "undetermined",
            "unknown_runtime_value",
            component_ids=candidate_ids,
            reasons=unknown_reasons + reset_reasons,
        )
    if reset_reasons:
        return rule_assessment(
            "runtime_spacing_contract",
            "issue",
            "runtime_reset",
            component_ids=candidate_ids,
            reasons=reset_reasons,
        )
    return rule_assessment(
        "runtime_spacing_contract",
        "clear",
        "runtime_mapped",
        component_ids=candidate_ids,
    )


def edge_value_collapses_to_zero(value: object) -> bool:
    """Mirror the renderer cases that reset the complete edge value to zero."""

    if isinstance(value, list):
        return True
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        number = numeric(value)
        return number is None or number < 0
    if isinstance(value, str):
        return not is_dynamic_dsl_value(value)
    if not isinstance(value, dict):
        return False
    physical = {"top", "right", "bottom", "left"}
    if value and not (physical & set(value)):
        return True
    has_absolute = False
    has_percent = False
    for edge in physical:
        raw = value.get(edge)
        if isinstance(raw, str) and not is_dynamic_dsl_value(raw):
            percent = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)%\s*", raw)
            number = float(percent.group(1)) if percent else numeric(raw)
            if number is not None and number > 0:
                has_percent = has_percent or percent is not None
                has_absolute = has_absolute or percent is None
        elif isinstance(raw, (int, float)) and not isinstance(raw, bool):
            number = numeric(raw)
            has_absolute = has_absolute or (number is not None and number > 0)
    return has_absolute and has_percent


def evaluate_static_text_clip_risk(context: AestheticContext) -> list[dict[str, Any]]:
    """Warn when a literal text string cannot fit a fully static text box.

    This is deliberately a conservative estimate, not a font-shaping engine: it
    only emits when content, width, line count, font size and horizontal padding
    are all static. Dynamic text, adaptive size and unconstrained width are left
    to the real renderer/UCD review instead of being guessed.
    """

    diagnostics: list[dict[str, Any]] = []
    for component in context.components:
        component_id = component.get("id")
        component_type = component.get("component")
        styles = component.get("styles")
        if (
            component_type not in {"Text", "Button"}
            or not isinstance(component_id, str)
            or not isinstance(styles, dict)
            or not is_effectively_visible(
                component_id, context.components_by_id, context.parent_by_child
            )
        ):
            continue
        raw_content = visible_text_value(component)
        content = resolve_visible_text(component, context)
        width = numeric(styles.get("width"))
        font_size = numeric(styles.get("fontSize"))
        if font_size is None and "fontSize" in styles:
            continue
        if font_size is None:
            font_size = 16.0
        max_lines = static_max_lines(styles)
        padding = spacing_axis_total(styles.get("padding"), "width")
        if (
            content is None
            or width is None
            or padding is None
            or max_lines is None
            or max_lines <= 0
            or any(field in styles for field in ("minFontSize", "maxFontSize"))
        ):
            continue
        available = width - padding
        estimated = estimate_text_width(content, font_size)
        capacity = max(available, 0.0) * max_lines
        actual = {
            "componentId": component_id,
            "estimatedTextWidth": round(estimated, 2),
            "estimatedCapacity": round(capacity, 2),
            "width": width,
            "horizontalPadding": padding,
            "maxLines": max_lines,
            "fontSize": font_size,
        }
        if raw_content is not None and raw_content != content:
            actual["resolvedText"] = content
        if estimated > capacity * MIN_PROVABLE_TEXT_CLIP_RATIO + 1e-9:
            diagnostics.append(
                diagnostic(
                    "warning",
                    "AESTHETIC_TEXT_CLIP_RISK",
                    "静态文本长度超过可证明的文本框容量，存在截断、换行失控或省略号风险。",
                    json_pointer=f"/updateComponents/components/{context.source_index_by_id[component_id]}/styles",
                    actual=actual,
                    expected=(
                        "estimatedTextWidth > availableWidth * maxLines * "
                        f"{MIN_PROVABLE_TEXT_CLIP_RATIO:g} 才报告"
                    ),
                    fix_hint="缩短文案、增加可用宽度/行数，或在真实渲染中确认可接受的省略策略。",
                )
            )
        elif (
            max_lines == 1
            and capacity > 0
            and stable_width_text(content)
            and visible_character_count(content) >= 3
            and estimated > capacity * MIN_PROVABLE_TEXT_DENSITY_RATIO + 1e-9
        ):
            actual["estimatedUsageRatio"] = round(estimated / capacity, 3)
            diagnostics.append(
                diagnostic(
                    "warning",
                    "AESTHETIC_TEXT_DENSITY_HIGH",
                    "单行文字几乎占满或超过文本框，字面容易贴边并与相邻内容挤在一起。",
                    json_pointer=f"/updateComponents/components/{context.source_index_by_id[component_id]}/styles",
                    actual=actual,
                    expected=(
                        "稳定宽度文字的估算占用不超过可用宽度的 "
                        f"{int(MIN_PROVABLE_TEXT_DENSITY_RATIO * 100)}%。"
                    ),
                    fix_hint="增加文本框宽度、缩短文案，或拆分语义并增加明确间距。",
                )
            )
    return diagnostics


def evaluate_static_pill_content_bounds(
    context: AestheticContext,
) -> list[dict[str, Any]]:
    """Report only statically proven capsule content-boundary failures.

    The rule intentionally ignores non-Button pills, adaptive fonts, dynamic
    labels, missing padding declarations and shapes that are not explicit
    capsules.  The width estimate is a lower bound with additional overflow
    margin so borderline font-shaping cases are skipped.
    """

    diagnostics: list[dict[str, Any]] = []
    for component in context.components:
        component_id = component.get("id")
        styles = component.get("styles")
        component_type = component.get("component")
        if (
            component_type not in {"Button", "Text"}
            or not isinstance(component_id, str)
            or not isinstance(styles, dict)
            or "padding" not in styles
            or any(field in styles for field in ("minFontSize", "maxFontSize"))
            or not is_effectively_visible(
                component_id, context.components_by_id, context.parent_by_child
            )
        ):
            continue
        if component_type == "Text" and not any(
            field in styles
            for field in ("backgroundColor", "linearGradient", "borderColor", "borderWidth")
        ):
            continue
        content = resolve_visible_text(component, context)
        width = numeric(styles.get("width"))
        height = numeric(styles.get("height"))
        radius = numeric(styles.get("borderRadius"))
        font_size = numeric(styles.get("fontSize"))
        max_lines = static_max_lines(styles)
        horizontal_padding = spacing_axis_total(styles.get("padding"), "width")
        vertical_padding = spacing_axis_total(styles.get("padding"), "height")
        if (
            content is None
            or width is None
            or height is None
            or width < height
            or radius is None
            or radius + 0.5 < min(height / 2.0, 8.0)
            or font_size is None
            or max_lines is None
            or max_lines < 1
            or horizontal_padding is None
            or vertical_padding is None
        ):
            continue
        available_width = width - horizontal_padding
        available_height = height - vertical_padding
        minimum_text_width = estimate_minimum_text_width(content, font_size)
        estimated_text_width = estimate_text_width(content, font_size)
        width_requires_wrap = (
            available_width <= 0
            or estimated_text_width > available_width * 1.1 + 1e-9
        )
        required_lines = (
            max(1, math.ceil(estimated_text_width / available_width - 1e-9))
            if width_requires_wrap and available_width > 0
            else 1
        )
        minimum_text_height = font_size * (
            0.7 if required_lines == 1 else required_lines
        )
        horizontal_overflow = (
            available_width <= 0
            or required_lines > max_lines
            or minimum_text_width
            > max(available_width, 0.0) * max_lines * 1.15
        )
        vertical_overflow = (
            available_height <= 0
            or minimum_text_height > max(available_height, 0.0) * 1.15
        )
        if not horizontal_overflow and not vertical_overflow:
            continue
        diagnostics.append(
            diagnostic(
                "warning",
                "AESTHETIC_PILL_CONTENT_OVERFLOW",
                "静态胶囊的可用内容区域无法容纳单行按钮文字，文字可能顶边或越界。",
                json_pointer=(
                    "/updateComponents/components/"
                    f"{context.source_index_by_id[component_id]}/styles"
                ),
                actual={
                    "componentId": component_id,
                    "width": width,
                    "height": height,
                    "borderRadius": radius,
                    "horizontalPadding": horizontal_padding,
                    "verticalPadding": vertical_padding,
                    "availableWidth": round(available_width, 2),
                    "availableHeight": round(available_height, 2),
                    "minimumEstimatedTextWidth": round(minimum_text_width, 2),
                    "minimumEstimatedTextHeight": round(minimum_text_height, 2),
                    "estimatedTextWidth": round(estimated_text_width, 2),
                    "requiredLines": required_lines,
                    "maxLines": max_lines,
                    "fontSize": font_size,
                },
                expected="胶囊内容区应以至少 15% 余量容纳保守文字尺寸下界。",
                fix_hint="减小显式 padding、增加胶囊宽高或缩短文案；动态/自适应字体应交给真实渲染复核。",
            )
        )
    return diagnostics


def visible_text_value(component: dict[str, Any]) -> str | None:
    field = "label" if component.get("component") == "Button" else "content"
    value = component.get(field)
    return value if isinstance(value, str) and value.strip() else None


def static_max_lines(styles: dict[str, Any]) -> float | None:
    """Return the protocol default only when maxLines is absent, never dynamic."""

    if "maxLines" not in styles:
        return 1.0
    return numeric(styles.get("maxLines"))


DSL_TEXT_TOKEN = re.compile(
    r"\$\{(?P<path>/[^}]+)\}|(?P<quoted>'(?:\\.|[^'])*'|\"(?:\\.|[^\"])*\")|(?P<number>-?\d+(?:\.\d+)?)"
)


def resolve_visible_text(
    component: dict[str, Any], context: AestheticContext
) -> str | None:
    value = visible_text_value(component)
    if value is None or not is_dynamic_dsl_value(value):
        return value
    expression = value.strip()
    if not (expression.startswith("{{") and expression.endswith("}}")):
        return None
    expression = expression[2:-2].strip()
    parts: list[str] = []
    position = 0
    for match in DSL_TEXT_TOKEN.finditer(expression):
        separator = expression[position : match.start()]
        if separator.strip(" +()"):
            return None
        if match.group("path") is not None:
            resolved = resolve_data_path(context.data_model, match.group("path"))
            if resolved is None or isinstance(resolved, (dict, list)):
                return None
            parts.append(str(resolved))
        elif match.group("quoted") is not None:
            try:
                literal = ast.literal_eval(match.group("quoted"))
            except (SyntaxError, ValueError):
                return None
            if not isinstance(literal, str):
                return None
            parts.append(literal)
        else:
            parts.append(match.group("number"))
        position = match.end()
    if not parts or expression[position:].strip(" +()"):
        return None
    return "".join(parts)


def evaluate_inline_text_fragment_risk(
    context: AestheticContext,
) -> list[dict[str, Any]]:
    """Detect a provable isolated CJK prefix in a dynamic one-line button.

    This rule is structural: it never keys on a case ID or complete label text.
    The DSL must concatenate a quoted single CJK character plus whitespace with
    at least one resolvable data path containing a sufficiently long body.
    """

    diagnostics: list[dict[str, Any]] = []
    for component in context.components:
        component_id = component.get("id")
        styles = component.get("styles")
        raw_label = visible_text_value(component)
        if (
            component.get("component") != "Button"
            or not isinstance(component_id, str)
            or not isinstance(styles, dict)
            or raw_label is None
            or not is_dynamic_dsl_value(raw_label)
            or static_max_lines(styles) != 1.0
            or not is_effectively_visible(
                component_id, context.components_by_id, context.parent_by_child
            )
        ):
            continue
        expression = raw_label.strip()
        if not (expression.startswith("{{") and expression.endswith("}}")):
            continue
        expression = expression[2:-2].strip()
        fragments: list[str] = []
        body_parts: list[str] = []
        token_kinds: list[str] = []
        for match in DSL_TEXT_TOKEN.finditer(expression):
            if match.group("path") is not None:
                token_kinds.append("path")
                resolved = resolve_data_path(context.data_model, match.group("path"))
                if resolved is None or isinstance(resolved, (dict, list)):
                    body_parts = []
                    break
                body_parts.append(str(resolved))
            elif match.group("quoted") is not None:
                token_kinds.append("literal")
                try:
                    literal = ast.literal_eval(match.group("quoted"))
                except (SyntaxError, ValueError):
                    continue
                if isinstance(literal, str) and re.fullmatch(
                    r"[\u3400-\u9fff]\s+", literal
                ):
                    fragments.append(literal.rstrip())
            else:
                token_kinds.append("number")
        resolved_label = resolve_visible_text(component, context)
        body = "".join(body_parts)
        if (
            len(fragments) != 1
            or not body_parts
            or not token_kinds
            or token_kinds[0] != "literal"
            or resolved_label is None
            or "\n" in resolved_label
            or visible_character_count(body) < 5
        ):
            continue
        diagnostics.append(
            diagnostic(
                "warning",
                "AESTHETIC_TEXT_FRAGMENT_CLIP_RISK",
                "动态单行按钮由孤立单字片段与较长正文拼接，存在可见字形断裂或裁切风险。",
                json_pointer=(
                    "/updateComponents/components/"
                    f"{context.source_index_by_id[component_id]}/label"
                ),
                actual={
                    "componentId": component_id,
                    "fragment": fragments[0],
                    "resolvedText": resolved_label,
                    "bodyVisibleCharacters": visible_character_count(body),
                    "maxLines": 1.0,
                    "fontSize": numeric(styles.get("fontSize")),
                },
                expected="动态单行按钮文案不应以孤立单个 CJK 字片段拼接长正文。",
                fix_hint="删除孤立前缀、改成完整短语，或把前缀与正文拆成有明确布局和间距的组件。",
            )
        )
    return diagnostics


def assess_inline_cjk_fragment_clip(
    context: AestheticContext,
    diagnostics: list[dict[str, Any]],
) -> dict[str, Any]:
    candidate_ids: list[str] = []
    unresolved_reasons: list[str] = []
    for component in context.components:
        component_id = component.get("id")
        styles = component.get("styles")
        raw_label = visible_text_value(component)
        if (
            component.get("component") != "Button"
            or not isinstance(component_id, str)
            or not isinstance(styles, dict)
            or raw_label is None
            or not is_dynamic_dsl_value(raw_label)
            or not is_effectively_visible(
                component_id, context.components_by_id, context.parent_by_child
            )
        ):
            continue
        expression = raw_label.strip()
        if not (expression.startswith("{{") and expression.endswith("}}")):
            continue
        expression = expression[2:-2].strip()
        matches = list(DSL_TEXT_TOKEN.finditer(expression))
        has_single_cjk_literal = False
        for match in matches:
            if match.group("quoted") is None:
                continue
            try:
                literal = ast.literal_eval(match.group("quoted"))
            except (SyntaxError, ValueError):
                literal = None
            if isinstance(literal, str) and re.fullmatch(
                r"[\u3400-\u9fff]\s+", literal
            ):
                has_single_cjk_literal = True
        if not has_single_cjk_literal:
            continue
        candidate_ids.append(component_id)
        if static_max_lines(styles) is None:
            unresolved_reasons.append(
                f"{component_id}: maxLines 无法静态求解"
            )
            continue
        prefix_candidate = bool(
            matches
            and matches[0].group("quoted") is not None
            and any(match.group("path") is not None for match in matches[1:])
        )
        if prefix_candidate and resolve_visible_text(component, context) is None:
            unresolved_reasons.append(
                f"{component_id}: 动态前缀表达式或数据路径无法完整解析"
            )

    if diagnostics:
        return rule_assessment(
            "inline_cjk_fragment_clip",
            "issue",
            "proven_text_contract",
            component_ids=candidate_ids,
            reasons=unresolved_reasons,
        )
    if not candidate_ids:
        return rule_assessment(
            "inline_cjk_fragment_clip", "not_applicable", "structural"
        )
    if unresolved_reasons:
        return rule_assessment(
            "inline_cjk_fragment_clip",
            "undetermined",
            "unknown_text_contract",
            component_ids=candidate_ids,
            reasons=unresolved_reasons,
        )
    return rule_assessment(
        "inline_cjk_fragment_clip",
        "clear",
        "proven_text_contract",
        component_ids=candidate_ids,
    )


def resolve_data_path(model: object, path: str) -> object | None:
    current = model
    for raw_token in path.lstrip("/").split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            return None
    return current


def stable_width_text(text: str) -> bool:
    """Use the tighter crowding threshold only for CJK/numeric fixture text."""

    return not any("A" <= character <= "Z" or "a" <= character <= "z" for character in text)


def visible_character_count(text: str) -> int:
    return sum(not character.isspace() for character in text)


def is_dynamic_dsl_value(value: object) -> bool:
    return isinstance(value, str) and "{{" in value and "}}" in value


def estimate_text_width(text: str, font_size: float) -> float:
    """Fast, deterministic CJK/Latin width proxy for clear overflow cases."""

    units = 0.0
    for character in text:
        if character.isspace():
            units += 0.35
        elif ord(character) >= 0x2E80:
            units += 1.0
        elif character.isalnum():
            units += 0.6
        else:
            units += 0.45
    return units * font_size


def estimate_minimum_text_width(text: str, font_size: float) -> float:
    """Lower-bound proxy used only for obvious single-line capsule failures."""

    units = 0.0
    for character in text:
        if character.isspace():
            units += 0.2
        elif ord(character) >= 0x2E80:
            units += 0.75
        elif character.isalnum():
            units += 0.42
        else:
            units += 0.28
    return units * font_size


def evaluate_action_target_size(context: AestheticContext) -> list[dict[str, Any]]:
    """Check only statically sized Button controls; unknown targets are not guessed."""

    diagnostics: list[dict[str, Any]] = []
    for component in context.components:
        component_id = component.get("id")
        styles = component.get("styles")
        if (
            not is_action_container(component)
            or not isinstance(component_id, str)
            or not isinstance(styles, dict)
            or not is_effectively_visible(
                component_id, context.components_by_id, context.parent_by_child
            )
        ):
            continue
        width, height = numeric(styles.get("width")), numeric(styles.get("height"))
        if width is None or height is None or (width >= 24 and height >= 24):
            continue
        diagnostics.append(
            diagnostic(
                "warning",
                "AESTHETIC_ACTION_TOO_SMALL",
                "静态按钮热区小于 24×24vp，容易误触且不利于可用性。",
                json_pointer=f"/updateComponents/components/{context.source_index_by_id[component_id]}/styles",
                actual={"componentId": component_id, "width": width, "height": height},
                expected={"minWidth": 24, "minHeight": 24},
                fix_hint="将可点击区域扩展到至少 24×24vp；视觉图标可小，但热区不应随之缩小。",
            )
        )
    return diagnostics


def evaluate_false_affordance(context: AestheticContext) -> list[dict[str, Any]]:
    """Find static Text pills that visually resemble a button but expose no action.

    It intentionally reports a risk rather than a hard error: tags can be valid
    static content, while the result gives UCD a precise review target.
    """

    risks: list[str] = []
    for component in context.components:
        component_id = component.get("id")
        styles = component.get("styles")
        if (
            component.get("component") != "Text"
            or not isinstance(component_id, str)
            or not isinstance(styles, dict)
            or visible_text_value(component) is None
            or not is_effectively_visible(
                component_id, context.components_by_id, context.parent_by_child
            )
        ):
            continue
        has_surface = "backgroundColor" in styles or "linearGradient" in styles
        has_pill_shape = (numeric(styles.get("borderRadius")) or 0) > 0
        has_box = numeric(styles.get("width")) is not None and numeric(styles.get("height")) is not None
        if has_surface and has_pill_shape and has_box and not has_effective_action(
            component_id, context
        ):
            risks.append(component_id)
    if not risks:
        return []
    return [
        diagnostic(
            "warning",
            "AESTHETIC_AFFORDANCE_FALSE_POSITIVE",
            "静态文字呈现为可点击 pill/按钮样式，但 DSL 未声明动作，存在假按钮风险。",
            json_pointer="/updateComponents/components",
            actual={"componentIds": risks},
            expected="视觉上像按钮的元素应声明可用动作，或改成明显的非交互标签样式。",
            fix_hint="补充真实可用动作，或去除按钮式背景、固定热区和过强圆角暗示。",
        )
    ]


def evaluate_information_hierarchy(context: AestheticContext) -> list[dict[str, Any]]:
    text_items: list[tuple[str, str, float]] = []
    for component in context.components:
        component_id, component_type, styles = (
            component.get("id"),
            component.get("component"),
            component.get("styles"),
        )
        if (
            component_type not in {"Text", "Button"}
            or not isinstance(component_id, str)
            or not isinstance(styles, dict)
            or visible_text_value(component) is None
            or not is_effectively_visible(
                component_id, context.components_by_id, context.parent_by_child
            )
        ):
            continue
        size = numeric(styles.get("fontSize"))
        if size is None and "fontSize" not in styles:
            size = 16.0
        if size is None:
            continue
        weight = normalize_font_weight(styles.get("fontWeight"), component_type)
        # A bounded, explainable proxy for visual dominance; not a visual score.
        prominence = size * (1.0 + max(weight - 400.0, 0.0) / 1000.0)
        text_items.append(
            (
                component_id,
                "action" if has_effective_action(component_id, context) else str(component_type),
                prominence,
            )
        )

    if len(text_items) < 2:
        return []
    diagnostics: list[dict[str, Any]] = []
    scores = sorted(score for _, _, score in text_items)
    maximum, median = scores[-1], scores[len(scores) // 2]
    if len(text_items) >= 3 and median > 0 and maximum / median < 1.25:
        diagnostics.append(
            diagnostic(
                "warning",
                "AESTHETIC_HIERARCHY_NO_PRIMARY",
                "多个可见文本的静态字号/字重相近，缺少可计算的主信息焦点。",
                json_pointer="/updateComponents/components",
                actual={"prominence": {component_id: round(score, 2) for component_id, _, score in text_items}},
                expected="主信息应在字号或字重上与支撑信息形成明确差异。",
                fix_hint="强化一个主信息，降低辅助文字的字号或字重，避免所有内容同等抢眼。",
            )
        )
    primary_items = [item for item in text_items if item[2] >= maximum * 0.9]
    if len(primary_items) >= 3:
        diagnostics.append(
            diagnostic(
                "warning",
                "AESTHETIC_HIERARCHY_TOO_MANY_PRIMARY",
                "同一卡片存在多个同等强度的主信息，阅读顺序可能失焦。",
                json_pointer="/updateComponents/components",
                actual={"primaryComponentIds": [item[0] for item in primary_items], "maxProminence": round(maximum, 2)},
                expected="通常仅保留一个主信息；并列主信息需要明确分组或降低其中一项。",
                fix_hint="选定唯一主信息，其余改为标题、状态或支撑层级。",
            )
        )
    action_scores = [score for _, kind, score in text_items if kind == "action"]
    content_scores = [score for _, kind, score in text_items if kind != "action"]
    if action_scores and content_scores and max(action_scores) > max(content_scores) * 1.2:
        diagnostics.append(
            diagnostic(
                "warning",
                "AESTHETIC_HIERARCHY_ACTION_OVER_PRIMARY",
                "CTA 的静态文字强度明显超过内容主信息，操作可能压过卡片主题。",
                json_pointer="/updateComponents/components",
                actual={"maxActionProminence": round(max(action_scores), 2), "maxContentProminence": round(max(content_scores), 2)},
                expected="CTA 应支撑主信息，而不是在字号/字重上压过主题。",
                fix_hint="降低 CTA 字号/字重，或增强内容主信息；保留颜色作为动作识别即可。",
            )
        )
    return diagnostics


def evaluate_small_card_density(context: AestheticContext) -> list[dict[str, Any]]:
    root_id = next(
        (component_id for component_id in context.components_by_id if component_id not in context.parent_by_child),
        None,
    )
    root = context.components_by_id.get(root_id, {}) if root_id else {}
    styles = root.get("styles") if isinstance(root, dict) else None
    if not isinstance(styles, dict):
        return []
    compact_grid = infer_compact_card_grid(root, context)
    if compact_grid is None:
        return []
    width, height, grid_source = compact_grid
    visible_content_units = [
        component.get("id")
        for component in context.components
        if component.get("id") != root_id
        and isinstance(component.get("id"), str)
        and is_density_content_unit(component)
        and is_effectively_visible(
            component["id"], context.components_by_id, context.parent_by_child
        )
    ]
    if len(visible_content_units) <= 10:
        return []
    return [
        diagnostic(
            "warning",
            "AESTHETIC_LAYOUT_DENSITY_HIGH",
            "紧凑卡片的可见内容单元过多，存在信息拥挤与点击误导风险。",
            json_pointer="/updateComponents/components",
            actual={
                "cardGrid": {"width": width, "height": height, "source": grid_source},
                "visibleContentUnitCount": len(visible_content_units),
                "componentIds": visible_content_units,
            },
            expected="短边不超过 180vp、长边不超过 320vp 的紧凑卡片，优先收敛到 10 个以内可见内容单元；复杂内容需真实渲染复核。",
            fix_hint="合并重复标签、隐藏次要装饰，或将详情引导至点击后的下一层。",
        )
    ]


def infer_compact_card_grid(
    root: dict[str, Any], context: AestheticContext
) -> tuple[float, float, str] | None:
    """Infer a compact logical grid without requiring an invalid fixed root.

    Runtime-correct Form DSL uses ``matchParent`` on the root.  The first direct
    layout child still commonly owns the fixed content grid (for example 314×146
    in a 2×4 Form), so use it only as a bounded density hint.
    """

    root_styles = root.get("styles") if isinstance(root, dict) else None
    if isinstance(root_styles, dict):
        width, height = numeric(root_styles.get("width")), numeric(root_styles.get("height"))
        if is_compact_grid(width, height):
            return width, height, "root"

    children = root.get("children") if isinstance(root, dict) else None
    if not isinstance(children, list):
        return None
    candidates: list[tuple[float, float, str]] = []
    for child_id in children:
        child = context.components_by_id.get(child_id) if isinstance(child_id, str) else None
        child_styles = child.get("styles") if isinstance(child, dict) else None
        if not isinstance(child_styles, dict):
            continue
        width, height = numeric(child_styles.get("width")), numeric(child_styles.get("height"))
        if is_compact_grid(width, height):
            candidates.append((width, height, str(child_id)))
    if not candidates:
        return None
    width, height, child_id = max(candidates, key=lambda item: item[0] * item[1])
    return width, height, f"directChild:{child_id}"


def is_compact_grid(width: float | None, height: float | None) -> bool:
    if width is None or height is None:
        return False
    return min(width, height) <= 180 and max(width, height) <= 320


def is_density_content_unit(component: dict[str, Any]) -> bool:
    component_type = component.get("component")
    if component_type in {"Text", "Button"}:
        return has_visible_text(component)
    if component_type != "Image":
        return False
    styles = component.get("styles")
    if not isinstance(styles, dict):
        return False
    width, height = numeric(styles.get("width")), numeric(styles.get("height"))
    return width is not None and height is not None and min(width, height) >= 8


def iter_static_style_colors(styles: dict[str, Any]) -> list[RGBA]:
    colors: list[RGBA] = []
    for field in COLOR_STYLE_FIELDS:
        parsed = parse_hex_color(styles.get(field))
        if parsed is not None:
            colors.append(parsed)
    gradient = styles.get("linearGradient")
    if isinstance(gradient, dict) and isinstance(gradient.get("colors"), list):
        for stop in gradient["colors"]:
            if isinstance(stop, list) and stop:
                parsed = parse_hex_color(stop[0])
                if parsed is not None:
                    colors.append(parsed)
    return colors


def chromatic_hue_family(color: RGBA) -> int | None:
    hue = chromatic_hue_degrees(color)
    return int(hue // 30) % 12 if hue is not None else None


def chromatic_hue_degrees(color: RGBA) -> float | None:
    red, green, blue, alpha = color
    maximum = max(red, green, blue)
    minimum = min(red, green, blue)
    chroma = maximum - minimum
    if alpha < 0.6 or maximum < 0.2 or chroma < 0.2:
        return None
    if maximum == red:
        hue = ((green - blue) / chroma) % 6
    elif maximum == green:
        hue = (blue - red) / chroma + 2
    else:
        hue = (red - green) / chroma + 4
    return (hue * 60) % 360


def minimum_circular_hue_span(hues: list[float]) -> float:
    if len(hues) <= 1:
        return 0.0
    ordered = sorted(hue % 360 for hue in hues)
    gaps = [
        ordered[index + 1] - ordered[index]
        for index in range(len(ordered) - 1)
    ]
    gaps.append(ordered[0] + 360 - ordered[-1])
    return 360 - max(gaps)


def build_report(
    components: list[dict[str, Any]],
    text_like_count: int,
    checked_count: int,
    diagnostics: list[dict[str, Any]],
    thresholds: Thresholds,
) -> dict[str, Any]:
    error_count = sum(item["severity"] == "error" for item in diagnostics)
    warning_count = sum(item["severity"] == "warning" for item in diagnostics)
    needs_review_count = sum(
        item["code"] == "AESTHETIC_COLOR_CONTRAST_UNDETERMINED"
        for item in diagnostics
    )
    status = (
        "fail"
        if error_count
        else "needs_review"
        if needs_review_count
        else "pass_with_warnings"
        if warning_count
        else "pass"
    )
    return {
        "schemaVersion": "0.2",
        "status": status,
        "summary": {
            "componentCount": len(components),
            "textLikeCount": text_like_count,
            "checkedCount": checked_count,
            "errorCount": error_count,
            "warningCount": warning_count,
            "needsReviewCount": needs_review_count,
        },
        "thresholds": {
            "normalTextMin": thresholds.normal_text_min,
            "largeTextMin": thresholds.large_text_min,
            "criticalMin": thresholds.critical_min,
            "largeFontSize": thresholds.large_font_size,
            "largeBoldFontSize": thresholds.large_bold_font_size,
            "largeBoldFontWeight": thresholds.large_bold_font_weight,
            "maxChromaticFamilies": thresholds.max_chromatic_families,
            "maxGradientSurfaces": thresholds.max_gradient_surfaces,
            "maxGradientStops": thresholds.max_gradient_stops,
            "maxTranslucentSurfaceLayers": thresholds.max_translucent_surface_layers,
            "maxFontSizeLevels": thresholds.max_font_size_levels,
            "maxRadiusValues": thresholds.max_radius_values,
            "maxShadowedComponents": thresholds.max_shadowed_components,
            "maxBorderWidthValues": thresholds.max_border_width_values,
            "maxNestedSurfaces": thresholds.max_nested_surfaces,
        },
        "diagnostics": diagnostics,
    }


def rule_assessment(
    rule_id: str,
    verdict: str,
    certainty: str,
    *,
    component_ids: list[str] | None = None,
    reasons: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "ruleId": rule_id,
        "applicability": (
            "not_applicable" if verdict == "not_applicable" else "applicable"
        ),
        "verdict": verdict,
        "certainty": certainty,
        "componentIds": component_ids or [],
        "reasons": reasons or [],
    }


def attach_rule_assessments(
    report: dict[str, Any], assessments: list[dict[str, Any]]
) -> None:
    report["ruleAssessments"] = assessments
    undetermined_count = sum(
        item.get("verdict") == "undetermined" for item in assessments
    )
    summary = dict(report.get("summary", {}))
    summary["generalizationUndeterminedCount"] = undetermined_count
    summary["needsReviewCount"] = (
        int(summary.get("needsReviewCount", 0)) + undetermined_count
    )
    report["summary"] = summary
    if undetermined_count and report.get("status") not in {"fail"}:
        report["status"] = "needs_review"


def has_visible_text(component: dict[str, Any]) -> bool:
    field = "label" if component.get("component") == "Button" else "content"
    value = component.get(field)
    if isinstance(value, str):
        return bool(value.strip())
    return value is not None


def component_is_statically_hidden(component: dict[str, Any]) -> bool:
    styles = component.get("styles")
    return isinstance(styles, dict) and styles.get("visibility") in {"hidden", "none"}


def is_effectively_visible(
    component_id: str,
    components_by_id: dict[str, dict[str, Any]],
    parent_by_child: dict[str, str],
) -> bool:
    current_id: str | None = component_id
    while current_id is not None:
        component = components_by_id.get(current_id, {})
        if component_is_statically_hidden(component):
            return False
        current_id = parent_by_child.get(current_id)
    return True


def resolve_background_candidates(
    component_id: str,
    components_by_id: dict[str, dict[str, Any]],
    parent_by_child: dict[str, str],
) -> tuple[list[RGBA], list[str], list[str]]:
    ancestry: list[str] = []
    current_id: str | None = component_id
    while current_id:
        ancestry.append(current_id)
        current_id = parent_by_child.get(current_id)

    candidates: list[RGBA] = []
    base_known = False
    descriptions: list[str] = []
    uncertainty: list[str] = []
    requires_solid_cover = False
    path = list(reversed(ancestry))
    for path_index, ancestor_id in enumerate(path):
        component = components_by_id.get(ancestor_id, {})
        styles = component.get("styles", {}) if isinstance(component, dict) else {}
        if not isinstance(styles, dict):
            continue

        if "backgroundImage" in styles:
            candidates = []
            base_known = False
            descriptions.append(f"{ancestor_id}:backgroundImage")
            uncertainty.append(f"{ancestor_id} 使用 backgroundImage")
            requires_solid_cover = True
        else:
            layer_kind = (
                "gradient"
                if "linearGradient" in styles
                else "solid"
                if "backgroundColor" in styles
                else ""
            )
            layer_values, layer_description, layer_uncertainty = background_layer(styles)
            if layer_uncertainty:
                candidates = []
                base_known = False
                uncertainty.append(f"{ancestor_id} {layer_uncertainty}")
                requires_solid_cover = True
            elif layer_values:
                descriptions.append(f"{ancestor_id}:{layer_description}")
                if all(layer[3] >= 0.999 for layer in layer_values):
                    if requires_solid_cover and (
                        layer_kind != "solid"
                        or not solid_layer_can_clear_image_taint(styles)
                    ):
                        candidates = []
                        base_known = False
                        uncertainty.append(
                            f"{ancestor_id} 的背景无法证明完整遮住图片像素"
                        )
                    else:
                        candidate_count = len(layer_values)
                        if candidate_count > MAX_BACKGROUND_CANDIDATES:
                            candidates = []
                            base_known = False
                            requires_solid_cover = True
                            uncertainty.append(
                                f"{ancestor_id} 的背景候选数量超过安全上限"
                            )
                        else:
                            candidates = list(layer_values)
                            base_known = True
                            requires_solid_cover = False
                elif base_known and candidates:
                    parent_candidates = list(candidates)
                    combination_count = len(layer_values) * len(parent_candidates)
                    candidate_count = combination_count
                    if candidate_count > MAX_BACKGROUND_CANDIDATES:
                        candidates = []
                        base_known = False
                        requires_solid_cover = True
                        uncertainty.append(
                            f"{ancestor_id} 的透明背景组合数 {combination_count} "
                            f"超过安全上限 {MAX_BACKGROUND_CANDIDATES}"
                        )
                    else:
                        candidates = [
                            composite(layer, background)
                            for layer in layer_values
                            for background in parent_candidates
                        ]
                else:
                    candidates = []
                    base_known = False
                    uncertainty.append(f"{ancestor_id} 的半透明背景缺少可确定底色")
                    requires_solid_cover = True

        branch_id = path[path_index + 1] if path_index + 1 < len(path) else None
        sibling_tainted, sibling_cover, visual_siblings = stack_sibling_effect(
            component, branch_id, components_by_id
        )
        if sibling_tainted:
            candidates = []
            base_known = False
            requires_solid_cover = True
            descriptions.append(
                f"{ancestor_id}:stackSiblings({','.join(visual_siblings)})"
            )
            uncertainty.append(
                f"{ancestor_id} 的 Stack 分支后方存在视觉兄弟层："
                + ", ".join(visual_siblings)
            )
        elif sibling_cover is not None:
            candidates = [sibling_cover]
            base_known = True
            requires_solid_cover = False
            descriptions.append(f"{ancestor_id}:opaqueSolidStackCover")
    return candidates if base_known else [], descriptions, uncertainty


def solid_layer_can_clear_image_taint(styles: dict[str, Any]) -> bool:
    if styles.get("visibility") not in (None, "visible"):
        return False
    return shape_value_is_zero(styles.get("borderRadius"))


def shape_value_is_zero(value: object) -> bool:
    if value is None:
        return True
    number = numeric(value)
    if number is not None:
        return abs(number) < 1e-9
    if isinstance(value, dict):
        return all(shape_value_is_zero(item) for item in value.values())
    return False


def stack_sibling_effect(
    component: dict[str, Any],
    branch_id: str | None,
    components_by_id: dict[str, dict[str, Any]],
) -> tuple[bool, RGBA | None, list[str]]:
    if component.get("component") != "Stack" or not isinstance(branch_id, str):
        return False, None, []
    children = component.get("children")
    if not isinstance(children, list) or branch_id not in children:
        return False, None, []
    tainted = False
    cover: RGBA | None = None
    visual_siblings: list[str] = []
    for sibling_id in children[: children.index(branch_id)]:
        if not isinstance(sibling_id, str):
            continue
        if not subtree_has_visual_layer(sibling_id, components_by_id, set()):
            continue
        visual_siblings.append(sibling_id)
        sibling = components_by_id.get(sibling_id, {})
        proven_cover = proven_full_opaque_solid_cover(sibling, component)
        if proven_cover is not None:
            tainted = False
            cover = proven_cover
        else:
            tainted = True
            cover = None
    return tainted, cover, visual_siblings


def proven_full_opaque_solid_cover(
    sibling: dict[str, Any], stack: dict[str, Any]
) -> RGBA | None:
    if sibling.get("component") != "Text" or child_component_ids(sibling):
        return None
    content = sibling.get("content")
    if not isinstance(content, str) or content.strip():
        return None
    sibling_styles = sibling.get("styles")
    stack_styles = stack.get("styles")
    if not isinstance(sibling_styles, dict) or not isinstance(stack_styles, dict):
        return None
    safe_style_fields = {
        "width",
        "height",
        "backgroundColor",
        "visibility",
        "maxLines",
    }
    if set(sibling_styles) - safe_style_fields:
        return None
    if sibling_styles.get("visibility") not in (None, "visible"):
        return None
    color = parse_hex_color(sibling_styles.get("backgroundColor"))
    if color is None or color[3] < 0.999:
        return None
    stack_size_can_differ = any(
        field in stack_styles
        for field in ("constraintSize", "layoutWeight", "flexGrow", "flexShrink")
    )
    if not dimension_covers(
        sibling_styles.get("width"),
        stack_styles.get("width"),
        stack_size_can_differ=stack_size_can_differ,
    ) or not dimension_covers(
        sibling_styles.get("height"),
        stack_styles.get("height"),
        stack_size_can_differ=stack_size_can_differ,
    ):
        return None
    return color


def dimension_covers(
    layer_value: object,
    stack_value: object,
    *,
    stack_size_can_differ: bool = False,
) -> bool:
    if isinstance(layer_value, str) and layer_value in {"matchParent", "100%"}:
        return True
    if stack_size_can_differ:
        return False
    layer_size = numeric(layer_value)
    stack_size = numeric(stack_value)
    return (
        layer_size is not None
        and stack_size is not None
        and layer_size >= stack_size
    )


def subtree_has_visual_layer(
    component_id: str,
    components_by_id: dict[str, dict[str, Any]],
    visited: set[str],
) -> bool:
    if component_id in visited:
        return False
    visited.add(component_id)
    component = components_by_id.get(component_id, {})
    if component_is_statically_hidden(component):
        return False
    styles = component.get("styles", {}) if isinstance(component, dict) else {}
    if component.get("component") == "Image" or (
        isinstance(styles, dict)
        and any(
            field in styles
            for field in ("backgroundColor", "backgroundImage", "linearGradient")
        )
    ):
        return True
    return any(
        subtree_has_visual_layer(child_id, components_by_id, visited)
        for child_id in child_component_ids(component)
    )


def child_component_ids(component: dict[str, Any]) -> list[str]:
    children = component.get("children")
    if isinstance(children, list):
        return [child_id for child_id in children if isinstance(child_id, str)]
    if isinstance(children, dict) and isinstance(children.get("componentId"), str):
        return [children["componentId"]]
    return []


def has_declared_action(component: dict[str, Any]) -> bool:
    """Match the protocol's component-level onClick carrier conservatively."""

    handlers = component.get("onClick")
    return isinstance(handlers, list) and bool(handlers)


def is_action_container(component: dict[str, Any]) -> bool:
    """Buttons are action-shaped; other components need a declared onClick."""

    return component.get("component") == "Button" or has_declared_action(component)


def has_effective_action(component_id: str, context: AestheticContext) -> bool:
    """A child inherits the click affordance of any visible ancestor container."""

    current_id: str | None = component_id
    while current_id is not None:
        component = context.components_by_id.get(current_id, {})
        if is_action_container(component):
            return True
        current_id = context.parent_by_child.get(current_id)
    return False


def background_layer(styles: dict[str, Any]) -> tuple[list[RGBA], str, str]:
    if "linearGradient" in styles:
        gradient = styles.get("linearGradient")
        if not isinstance(gradient, dict) or not isinstance(gradient.get("colors"), list):
            return [], "", "linearGradient 无法静态解析"
        colors: list[RGBA] = []
        labels: list[str] = []
        for stop in gradient["colors"]:
            if not (isinstance(stop, list) and len(stop) == 2):
                return [], "", "linearGradient stop 无法静态解析"
            parsed = parse_hex_color(stop[0])
            if parsed is None:
                return [], "", "linearGradient 颜色无法静态解析"
            colors.append(parsed)
            labels.append(str(stop[0]))
        return colors, "linearGradient(" + ",".join(labels) + ")", ""

    if "backgroundColor" in styles:
        value = styles.get("backgroundColor")
        parsed = parse_hex_color(value)
        if parsed is None:
            return [], "", "backgroundColor 无法静态解析"
        return [parsed], f"backgroundColor({value})", ""
    return [], "", ""


def parse_hex_color(value: object) -> RGBA | None:
    if not isinstance(value, str) or not value.startswith("#"):
        return None
    raw = value[1:]
    try:
        if len(raw) == 6:
            alpha = 255
            red, green, blue = int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
        elif len(raw) == 8:
            alpha = int(raw[0:2], 16)
            red, green, blue = int(raw[2:4], 16), int(raw[4:6], 16), int(raw[6:8], 16)
        else:
            return None
    except ValueError:
        return None
    return red / 255, green / 255, blue / 255, alpha / 255


def composite(foreground: RGBA, background: RGBA) -> RGBA:
    fg_red, fg_green, fg_blue, fg_alpha = foreground
    bg_red, bg_green, bg_blue, bg_alpha = background
    out_alpha = fg_alpha + bg_alpha * (1 - fg_alpha)
    if out_alpha == 0:
        return 0, 0, 0, 0
    return (
        (fg_red * fg_alpha + bg_red * bg_alpha * (1 - fg_alpha)) / out_alpha,
        (fg_green * fg_alpha + bg_green * bg_alpha * (1 - fg_alpha)) / out_alpha,
        (fg_blue * fg_alpha + bg_blue * bg_alpha * (1 - fg_alpha)) / out_alpha,
        out_alpha,
    )


def contrast_ratio(foreground: RGBA, background: RGBA) -> float | None:
    if background[3] < 0.999:
        return None
    visible_foreground = composite(foreground, background)
    foreground_luminance = relative_luminance(visible_foreground)
    background_luminance = relative_luminance(background)
    lighter = max(foreground_luminance, background_luminance)
    darker = min(foreground_luminance, background_luminance)
    return (lighter + 0.05) / (darker + 0.05)


def relative_luminance(color: RGBA) -> float:
    red, green, blue, _ = color
    return 0.2126 * linearize(red) + 0.7152 * linearize(green) + 0.0722 * linearize(blue)


def linearize(channel: float) -> float:
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, str):
        match = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)(?:vp|fp|px)?\s*", value)
        if match:
            number = float(match.group(1))
            return number if math.isfinite(number) else None
    return None


def normalize_font_weight(value: object, component_type: object) -> float:
    number = numeric(value)
    if number is not None:
        return number
    if isinstance(value, str):
        named_weights = {
            "lighter": 100.0,
            "normal": 400.0,
            "regular": 400.0,
            "medium": 500.0,
            "bold": 700.0,
            "bolder": 900.0,
        }
        if value in named_weights:
            return named_weights[value]
    return 500.0 if component_type == "Button" else 400.0


def smallest_possible_font_size(
    styles: dict[str, Any], declared_size: float
) -> tuple[float, bool]:
    smallest = declared_size
    uncertain = False
    for field in ("minFontSize", "maxFontSize"):
        if field not in styles:
            continue
        value = numeric(styles.get(field))
        if value is None:
            smallest = 0.0
            uncertain = True
        else:
            smallest = min(smallest, value)
    return smallest, uncertain


DIAGNOSTIC_LABELS = {
    "AESTHETIC_INPUT_READ_FAILED": "DSL 输入无法读取",
    "AESTHETIC_PRECONDITION_FAILED": "DSL 结构无法分析",
    "AESTHETIC_COLOR_CONTRAST_UNDETERMINED": "对比度无法静态判断",
    "AESTHETIC_COLOR_CONTRAST_LOW": "内容与背景对比度不足",
    "AESTHETIC_COLOR_PALETTE_TOO_COMPLEX": "颜色过多",
    "AESTHETIC_COLOR_ACCENT_OVERUSED": "强调色使用过多",
    "AESTHETIC_COLOR_ROLE_INCONSISTENT": "颜色角色不一致",
    "AESTHETIC_COLOR_GRADIENT_OVERCOMPLEX": "渐变过于复杂",
    "AESTHETIC_COLOR_ALPHA_STACK_COMPLEX": "透明层叠过多",
    "AESTHETIC_TYPO_TOO_MANY_LEVELS": "字体层级过多",
    "AESTHETIC_TYPO_BOLD_OVERUSED": "粗体使用过多",
    "AESTHETIC_STYLE_RADIUS_INCONSISTENT": "圆角规格不一致",
    "AESTHETIC_STYLE_SHADOW_OVERUSED": "阴影使用过多",
    "AESTHETIC_STYLE_STROKE_INCONSISTENT": "描边规格不一致",
    "AESTHETIC_STYLE_SURFACE_NESTING_EXCESSIVE": "内容背板嵌套过深",
    "AESTHETIC_LAYOUT_SPACING_NON_TOKEN": "间距未使用规范值",
    "AESTHETIC_LAYOUT_SPACING_MISSING": "间距缺失",
    "AESTHETIC_LAYOUT_SPACING_INCONSISTENT": "间距不一致",
    "AESTHETIC_LAYOUT_BOUNDS_OVERFLOW": "内容溢出",
    "AESTHETIC_CONTROL_GROUP_GAP_LOW": "相邻控件间距过小",
    "AESTHETIC_CONTROL_INTRINSIC_GAP_LOW": "控件实际间距过小",
    "AESTHETIC_TEXT_COLLISION_RISK": "相邻文字字形碰撞",
    "AESTHETIC_TEXT_GAP_LOW": "相邻文字间距过小",
    "AESTHETIC_TEXT_ICON_GAP_LOW": "文字与图标间距过小",
    "AESTHETIC_LAYOUT_EDGE_CLEARANCE_LOW": "边缘留白过小",
    "AESTHETIC_SURFACE_CONTENT_EDGE_CLEARANCE_LOW": "圆角表面内容贴边",
    "AESTHETIC_STACK_TEXT_IMAGE_OVERLAP": "文字与图片重叠",
    "AESTHETIC_LAYOUT_VERTICAL_DENSITY_HIGH": "内容区域拥挤",
    "AESTHETIC_TEXT_CLIP_RISK": "文字截断风险",
    "AESTHETIC_TEXT_FRAGMENT_CLIP_RISK": "单行文字片段裁切风险",
    "AESTHETIC_TEXT_DENSITY_HIGH": "文字区域拥挤",
    "AESTHETIC_PILL_CONTENT_OVERFLOW": "胶囊内容越界",
    "AESTHETIC_ACTION_TOO_SMALL": "控件尺寸过小",
    "AESTHETIC_AFFORDANCE_FALSE_POSITIVE": "静态元素具有错误点击暗示",
    "AESTHETIC_HIERARCHY_NO_PRIMARY": "关键内容不突出",
    "AESTHETIC_HIERARCHY_TOO_MANY_PRIMARY": "主信息过多",
    "AESTHETIC_HIERARCHY_ACTION_OVER_PRIMARY": "操作按钮压过主信息",
    "AESTHETIC_LAYOUT_DENSITY_HIGH": "信息密度过高",
    "AESTHETIC_ROUNDED_SURFACE_EDGE_SAFE_AREA_LOW": "按钮贴满父卡片内容盒",
    "AESTHETIC_ROUNDED_SURFACE_PAIR_GAP_LOW": "圆角表面相接或重叠",
    "AESTHETIC_ESTIMATED_TEXT_SURFACE_OVERLAP": "文字估算绘制区压住表面",
}

PUBLIC_DIAGNOSTIC_LABELS = {
    "AESTHETIC_LAYOUT_BOUNDS_OVERFLOW": "内容或文字重叠",
    "AESTHETIC_CONTROL_GROUP_GAP_LOW": "文字/控件贴边",
    "AESTHETIC_CONTROL_INTRINSIC_GAP_LOW": "文字/控件贴边",
    "AESTHETIC_TEXT_COLLISION_RISK": "内容或文字重叠",
    "AESTHETIC_TEXT_GAP_LOW": "文字区域拥挤",
    "AESTHETIC_TEXT_ICON_GAP_LOW": "文字/控件贴边",
    "AESTHETIC_TEXT_CLIP_RISK": "内容或文字重叠",
    "AESTHETIC_TEXT_FRAGMENT_CLIP_RISK": "内容或文字重叠",
    "AESTHETIC_TEXT_DENSITY_HIGH": "文字区域拥挤",
    "AESTHETIC_LAYOUT_VERTICAL_DENSITY_HIGH": "文字区域拥挤",
    "AESTHETIC_LAYOUT_EDGE_CLEARANCE_LOW": "文字/控件贴边",
    "AESTHETIC_SURFACE_CONTENT_EDGE_CLEARANCE_LOW": "文字/控件贴边",
    "AESTHETIC_STACK_TEXT_IMAGE_OVERLAP": "内容或文字重叠",
    "AESTHETIC_PILL_CONTENT_OVERFLOW": "文字/控件贴边",
    "AESTHETIC_ROUNDED_SURFACE_EDGE_SAFE_AREA_LOW": "文字/控件贴边",
    "AESTHETIC_ROUNDED_SURFACE_PAIR_GAP_LOW": "文字/控件贴边",
    "AESTHETIC_ESTIMATED_TEXT_SURFACE_OVERLAP": "内容或文字重叠",
}


def diagnostic(
    severity: str,
    code: str,
    message: str,
    *,
    line: int | None = None,
    json_pointer: str = "",
    logical_path: str = "",
    actual: Any = None,
    expected: Any = None,
    fix_hint: str = "",
) -> dict[str, Any]:
    result = {
        "severity": severity,
        "code": code,
        "label": DIAGNOSTIC_LABELS.get(code, message),
        "message": message,
        "line": line,
        "jsonPointer": json_pointer,
        "logicalPath": logical_path,
        "actual": actual,
        "expected": expected,
        "fixHint": fix_hint,
    }
    public_label = PUBLIC_DIAGNOSTIC_LABELS.get(code)
    result["publicLabel"] = public_label
    result["disposition"] = (
        "mapped_to_public_three_check" if public_label else "internal_or_out_of_scope"
    )
    return {key: value for key, value in result.items() if value not in (None, "")}


def public_report(report: dict[str, Any]) -> dict[str, Any]:
    """Return the V1 public delivery view while preserving internal evidence.

    Public diagnostics are limited to the three contracted visible-evidence labels.
    Internal/runtime diagnostics stay available under ``internalDiagnostics`` so
    callers can debug without counting them as public aesthetic issues.
    """

    public_diagnostics: list[dict[str, Any]] = []
    internal_diagnostics: list[dict[str, Any]] = []
    for item in report.get("diagnostics", []):
        public_label = item.get("publicLabel")
        if isinstance(public_label, str):
            public_item = dict(item)
            public_item["internalLabel"] = item.get("label")
            public_item["label"] = public_label
            public_diagnostics.append(public_item)
        else:
            internal_diagnostics.append(dict(item))

    result = dict(report)
    result["diagnostics"] = public_diagnostics
    result["internalDiagnostics"] = internal_diagnostics
    result["outputScope"] = "public"

    # Scope controls presentation only. Gate counts and status must remain those
    # produced by the full analysis, otherwise a hidden internal diagnostic can
    # silently turn a fail/needs_review result into pass.
    summary = dict(result.get("summary", {}))
    summary.update(
        {
            "publicDiagnosticCount": len(public_diagnostics),
            "internalDiagnosticCount": len(internal_diagnostics),
        }
    )
    result["summary"] = summary
    return result


def render_text(report: dict[str, Any]) -> str:
    lines = [f"status: {report['status']}"]
    if "contrast" in str(report.get("analysisProfile", "")):
        lines.append(
            "contrast checked: "
            f"{report['summary']['checkedCount']}/{report['summary']['textLikeCount']}"
        )
    gate_internal_diagnostics = [
        item
        for item in report.get("internalDiagnostics", [])
        if item.get("severity") == "error"
        or item.get("code") == "AESTHETIC_COLOR_CONTRAST_UNDETERMINED"
    ]
    rendered_diagnostics = [
        *report.get("diagnostics", []),
        *gate_internal_diagnostics,
    ]
    for index, item in enumerate(rendered_diagnostics, start=1):
        location = item.get("jsonPointer", "genui")
        lines.append("")
        lines.append(f"问题{index}：{item.get('label', item['message'])}")
        lines.append(f"等级：{item['severity'].upper()}")
        lines.append(f"代码：{item['code']}")
        lines.append(f"位置：{location}")
        lines.append(f"说明：{item['message']}")
        if item.get("actual") is not None:
            lines.append(
                "当前："
                + json.dumps(item["actual"], ensure_ascii=False, allow_nan=False)
            )
        if item.get("expected") is not None:
            lines.append(
                "期望："
                + json.dumps(item["expected"], ensure_ascii=False, allow_nan=False)
            )
        if item.get("fixHint"):
            lines.append(f"建议：{item['fixHint']}")
    for index, item in enumerate(
        (
            assessment
            for assessment in report.get("ruleAssessments", [])
            if assessment.get("verdict") == "undetermined"
        ),
        start=1,
    ):
        lines.append("")
        lines.append(f"待人工确认{index}：{item.get('ruleId', 'unknown_rule')}")
        reasons = item.get("reasons") or []
        if reasons:
            lines.append("原因：" + "；".join(str(reason) for reason in reasons))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Standalone DSL-only aesthetic risk validator")
    parser.add_argument(
        "path", nargs="?", default="-", help="genui JSONL file, fenced draft, or '-' for stdin"
    )
    parser.add_argument("--format", choices=["json", "text"], default="text")
    parser.add_argument(
        "--scope",
        choices=["public", "internal"],
        default="public",
        help="Public output exposes only the three contracted visible-evidence labels; internal keeps all diagnostics.",
    )
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failed exit code")
    parser.add_argument(
        "--allow-undetermined",
        action="store_true",
        help="Allow IMAGE/dynamic contrast cases to exit 0; default requires review.",
    )
    parser.add_argument(
        "--include-contrast",
        action="store_true",
        help="Also check text/background contrast when the effective background is provable.",
    )
    parser.add_argument(
        "--include-heuristics",
        action="store_true",
        help="Also emit subjective proxy rules such as palette complexity, hierarchy and density.",
    )
    parser.add_argument("--normal-min", type=float, default=4.5)
    parser.add_argument("--large-min", type=float, default=3.0)
    parser.add_argument("--critical-min", type=float, default=3.0)
    args = parser.parse_args()

    try:
        thresholds = Thresholds(
            normal_text_min=args.normal_min,
            large_text_min=args.large_min,
            critical_min=args.critical_min,
        )
    except ValueError as exc:
        parser.error(str(exc))

    try:
        raw = read_text(args.path)
    except OSError as exc:
        report = build_report(
            [],
            0,
            0,
            [
                diagnostic(
                    "error",
                    "AESTHETIC_INPUT_READ_FAILED",
                    "无法读取 DSL 输入文件。",
                    actual={
                        "path": args.path,
                        "error": exc.strerror or type(exc).__name__,
                    },
                    expected="存在且可读取的 JSONL、JSON array 或 Markdown genui 文件",
                    fix_hint="检查输入路径、文件权限，或使用 '-' 从 stdin 读取。",
                )
            ],
            thresholds,
        )
        attach_rule_assessments(report, [])
        report["analysisProfile"] = analysis_profile(
            args.include_contrast, args.include_heuristics
        )
    else:
        report = analyze(
            raw,
            thresholds,
            include_contrast=args.include_contrast,
            include_heuristics=args.include_heuristics,
        )
    if args.scope == "public":
        report = public_report(report)
    print(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
        if args.format == "json"
        else render_text(report)
    )
    if report["summary"]["errorCount"]:
        return 1
    if report["summary"]["needsReviewCount"] and not args.allow_undetermined:
        return 1
    if args.strict and report["summary"]["warningCount"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
