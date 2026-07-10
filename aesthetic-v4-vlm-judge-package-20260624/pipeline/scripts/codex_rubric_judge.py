#!/usr/bin/env python3
"""aesthetic-v4 rubric prompt factory.

This package intentionally exposes only the aesthetic-v4 prompt profile.
"""

from __future__ import annotations

import json
import re
from typing import Any

from aesthetic_contract import AXIS_WEIGHTS, clamp_score as contract_clamp_score


WEIGHTS: dict[str, float] = AXIS_WEIGHTS

OCCLUSION_OVERLAP_CHECK = "always_on"
QUALITY_SWITCHES_DEFAULT = {
    "adaptive_viewports": "off",
    "score_breakdown": "on",
    "designer_review": "off",
    "occlusion_overlap_check": OCCLUSION_OVERLAP_CHECK,
}
ADAPTIVE_VIEWPORTS_CHOICES = {"off", "on", "auto"}
ON_OFF_CHOICES = {"off", "on"}
OCCLUSION_TYPES = {
    "text_text",
    "text_graphic",
    "control_nav",
    "layer_zindex",
    "clipping_crop",
    "unknown",
}
OCCLUSION_SEVERITIES = {"minor", "moderate", "severe", "blocking"}
SEVERITY_RANK = {"minor": 1, "moderate": 2, "severe": 3, "blocking": 4}
OCCLUSION_SEVERITY_AXIS_CAPS = {"minor": 6.0, "moderate": 4.0, "severe": 2.0, "blocking": 0.0}
OCCLUSION_TYPE_AXES = {
    "text_text": ["typography", "composition_hierarchy", "detail_finish", "basic_usability"],
    "text_graphic": ["typography", "composition_hierarchy", "detail_finish", "basic_usability"],
    "control_nav": ["basic_usability", "composition_hierarchy", "detail_finish"],
    "layer_zindex": ["composition_hierarchy", "detail_finish", "basic_usability"],
    "clipping_crop": ["typography", "composition_hierarchy", "detail_finish", "basic_usability"],
    "unknown": ["composition_hierarchy", "detail_finish"],
}


def normalize_quality_switches(raw: Any) -> dict[str, str]:
    config = raw if isinstance(raw, dict) else {}
    adaptive = str(config.get("adaptive_viewports") or QUALITY_SWITCHES_DEFAULT["adaptive_viewports"]).strip().lower()
    score_breakdown = str(config.get("score_breakdown") or QUALITY_SWITCHES_DEFAULT["score_breakdown"]).strip().lower()
    designer_review = str(config.get("designer_review") or QUALITY_SWITCHES_DEFAULT["designer_review"]).strip().lower()
    if adaptive not in ADAPTIVE_VIEWPORTS_CHOICES:
        adaptive = QUALITY_SWITCHES_DEFAULT["adaptive_viewports"]
    if score_breakdown not in ON_OFF_CHOICES:
        score_breakdown = QUALITY_SWITCHES_DEFAULT["score_breakdown"]
    if designer_review not in ON_OFF_CHOICES:
        designer_review = QUALITY_SWITCHES_DEFAULT["designer_review"]
    return {
        "adaptive_viewports": adaptive,
        "score_breakdown": score_breakdown,
        "designer_review": designer_review,
        "occlusion_overlap_check": OCCLUSION_OVERLAP_CHECK,
    }


def quality_instruction_block(request: dict[str, Any]) -> str:
    config = normalize_quality_switches(request.get("quality_config"))
    designer_line = (
        "- designer_review=on：额外输出 designer_review，包含 pros / cons / suggestions 三组简短设计师建议。"
        if config["designer_review"] == "on"
        else "- designer_review=off：不要输出长篇 designer_review；final score 和 axis_scores 不受该开关影响。"
    )
    score_breakdown_line = (
        "- score_breakdown=on：输出 occlusion_score_impact；权重固定，只通过降低对应 axis_scores 体现扣分。"
        if config["score_breakdown"] == "on"
        else "- score_breakdown=off：内部仍按固定权重和 axis_scores 算分，但报告层可隐藏详细分项。"
    )
    return f"""
质量开关：
{json.dumps(config, ensure_ascii=False, sort_keys=True)}

遮挡/重叠检查是强制常开，不是可关闭选项：
- occlusion_overlap_check=always_on。评分前必须检查文字/文字、文字/图片或图标、按钮/输入框/导航、固定底部栏、图表或正文被遮挡。
- 如果发现遮挡或重叠，不要修改 rubric_weights；必须降低受影响的 axis_scores，并在 occlusion_findings 里写出 type / severity / target / evidence / affected_axes。
- occlusion_findings.type 只能使用：text_text、text_graphic、control_nav、layer_zindex、clipping_crop、unknown。
- 受影响轴按 severity 设上限：minor 最高 6.0，moderate 最高 4.0，severe 最高 2.0，blocking 必须为 0.0。
- occlusion_score_impact 必须能说明固定权重下的影响：对应 axis 的 score、weight、weighted_contribution 和 weighted_loss_from_max。
- severe/blocking 的核心阅读或核心操作失败必须标记为结构化硬缺陷；blocking 且核心内容不可读/不可操作时 rationale 以 ZERO_DEFECT: 开头。
- ZERO_DEFECT 不等于六轴全 0。必须按遮挡类型填写 affected_axes，并把这些相关 axis_scores 打到 0 或极低；未受影响的视觉/色彩等轴继续按截图可见质量评分。最终 score 必须由固定权重下的 axis_scores 加权得到。
{score_breakdown_line}
{designer_line}
""".strip()


def _short_text(value: Any, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def clamp_score(value: Any) -> float:
    return contract_clamp_score(value)


def normalize_occlusion_type(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace("/", "_").replace(" ", "_")
    aliases = {
        "text": "text_text",
        "text_overlap": "text_text",
        "text_text_overlap": "text_text",
        "text_on_text": "text_text",
        "text_image": "text_graphic",
        "text_image_icon": "text_graphic",
        "text_on_image": "text_graphic",
        "text_icon": "text_graphic",
        "image_text": "text_graphic",
        "graphic": "text_graphic",
        "chart": "text_graphic",
        "button": "control_nav",
        "button_blocked": "control_nav",
        "input": "control_nav",
        "input_blocked": "control_nav",
        "nav": "control_nav",
        "navigation": "control_nav",
        "interactive_blocked": "control_nav",
        "fixed_footer_blocking": "control_nav",
        "footer": "control_nav",
        "bottom_bar": "control_nav",
        "fixed_footer": "control_nav",
        "tab_bar": "control_nav",
        "zindex": "layer_zindex",
        "z_index": "layer_zindex",
        "layer": "layer_zindex",
        "overlay": "layer_zindex",
        "body": "layer_zindex",
        "content_blocked": "layer_zindex",
        "crop": "clipping_crop",
        "cropping": "clipping_crop",
        "clip": "clipping_crop",
        "clipping": "clipping_crop",
        "overflow": "clipping_crop",
        "truncated": "clipping_crop",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in OCCLUSION_TYPES else "unknown"


def normalize_occlusion_severity(value: Any, *, score: float | None = None, rationale: str = "") -> str:
    normalized = str(value or "").strip().lower()
    aliases = {
        "low": "minor",
        "mild": "minor",
        "light": "minor",
        "medium": "moderate",
        "major": "severe",
        "critical": "blocking",
        "zero_defect": "blocking",
        "hard_zero": "blocking",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized in OCCLUSION_SEVERITIES:
        return normalized
    text = rationale.casefold()
    if rationale.startswith("ZERO_DEFECT:"):
        return "blocking"
    if _contains_any(text, ("不可稳定阅读", "不可读", "无法辨认", "无法操作", "核心操作失败")):
        return "severe"
    if _contains_any(text, ("仍可读", "轻微", "局部", "粗糙感")):
        return "minor"
    if score is not None and score <= 2.0:
        return "severe"
    return "moderate"


def default_axes_for_occlusion(occlusion_type: str, severity: str) -> list[str]:
    del severity
    return list(OCCLUSION_TYPE_AXES.get(occlusion_type, OCCLUSION_TYPE_AXES["unknown"]))


def normalize_affected_axes(value: Any, occlusion_type: str, severity: str) -> list[str]:
    axes: list[str] = []
    if isinstance(value, list):
        for item in value:
            axis = str(item or "").strip()
            if axis in WEIGHTS and axis not in axes:
                axes.append(axis)
    for axis in default_axes_for_occlusion(occlusion_type, severity):
        if axis not in axes:
            axes.append(axis)
    return axes


def describes_non_occlusion(text: str) -> bool:
    return _contains_any(
        text,
        (
            "不遮挡",
            "未遮挡",
            "没有遮挡",
            "无遮挡",
            "不重叠",
            "无重叠",
            "不影响核心",
            "未影响核心",
            "不影响阅读",
            "不影响操作",
            "并未遮挡",
        ),
    )


def infer_occlusion_findings_from_rationale(
    rationale: str,
    *,
    score: float | None = None,
    viewport: str | None = None,
) -> list[dict[str, Any]]:
    text = rationale.casefold()
    if describes_non_occlusion(text) and not rationale.startswith("ZERO_DEFECT:"):
        return []
    has_issue = _contains_any(
        text,
        ("重叠", "覆盖", "遮挡", "遮住", "挡住", "裁切", "溢出", "不可读", "被压", "压在", "压到"),
    )
    if _contains_any(text, ("压住版面", "视觉系统缺席", "图表缺位", "chart 在截图中完全缺位", "素材缺失", "内容缺失")) and not _contains_any(
        text,
        ("重叠", "覆盖", "遮挡", "遮住", "挡住", "裁切", "溢出", "不可读", "被压", "压在", "压到"),
    ):
        has_issue = False
    if not has_issue and not rationale.startswith("ZERO_DEFECT:"):
        return []
    if rationale.startswith("ZERO_DEFECT:"):
        severity = "blocking"
    elif _contains_any(text, ("仍可读", "整体仍可读", "轻微")):
        severity = "minor"
    elif _contains_any(text, ("粗糙感", "底部列表还有被输入栏遮挡")):
        severity = "moderate"
    elif _contains_any(text, ("明显覆盖", "核心", "不可稳定阅读", "不可读", "严重")):
        severity = "severe"
    elif score is not None and score <= 1.5:
        severity = "severe"
    else:
        severity = "moderate"

    if _contains_any(text, ("图表", "chart", "折线图", "柱状图", "表格", "正文")):
        occlusion_type = "text_graphic"
        target = "chart/body content"
    elif _contains_any(text, ("底部固定", "固定底部", "bottom", "footer", "tab bar", "tabbar", "底部导航", "底部输入栏")):
        occlusion_type = "control_nav"
        target = "fixed footer or bottom bar"
    elif _contains_any(text, ("图片", "图像", "图形", "图标", "背景", "食物", "复杂")):
        occlusion_type = "text_graphic"
        target = "text over image/icon"
    elif _contains_any(text, ("按钮", "button", "输入", "input", "导航", "nav", "tab", "操作")):
        occlusion_type = "control_nav"
        target = "interactive control"
    elif _contains_any(text, ("文字", "标题", "正文", "说明", "列表")):
        occlusion_type = "text_text"
        target = "text block"
    else:
        occlusion_type = "unknown"
        target = "visible content"

    finding = {
        "type": occlusion_type,
        "severity": severity,
        "target": target,
        "evidence": _short_text(rationale),
        "affected_axes": default_axes_for_occlusion(occlusion_type, severity),
    }
    if viewport:
        finding["viewport"] = viewport
    return [finding]


def normalize_occlusion_findings(
    payload: dict[str, Any],
    *,
    rationale: str | None = None,
    axis_scores: dict[str, float] | None = None,
    score: float | None = None,
    viewport: str | None = None,
) -> list[dict[str, Any]]:
    del axis_scores
    raw = payload.get("occlusion_findings")
    findings: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            evidence = _short_text(item.get("evidence") or item.get("reason") or rationale)
            if describes_non_occlusion(evidence.casefold()) and not (rationale or "").startswith("ZERO_DEFECT:"):
                continue
            occlusion_type = normalize_occlusion_type(item.get("type"))
            severity = normalize_occlusion_severity(item.get("severity"), score=score, rationale=evidence or rationale or "")
            finding = {
                "type": occlusion_type,
                "severity": severity,
                "target": _short_text(item.get("target") or "visible content", 120),
                "evidence": evidence,
                "affected_axes": normalize_affected_axes(item.get("affected_axes"), occlusion_type, severity),
            }
            item_viewport = item.get("viewport") or viewport
            if item_viewport:
                finding["viewport"] = str(item_viewport)
            findings.append(finding)
    inferred = infer_occlusion_findings_from_rationale(rationale or "", score=score, viewport=viewport)
    if not findings:
        findings = inferred
    return findings


def highest_severity(values: list[str]) -> str:
    if not values:
        return "minor"
    return max(values, key=lambda item: SEVERITY_RANK.get(item, 0))


def build_occlusion_score_impact(axis_scores: dict[str, float], findings: list[dict[str, Any]]) -> dict[str, Any]:
    weighted_score = weighted_axis_score(axis_scores)
    axis_to_findings: dict[str, list[dict[str, Any]]] = {}
    for finding in findings:
        axes = finding.get("affected_axes") if isinstance(finding.get("affected_axes"), list) else []
        for axis in axes:
            if axis in WEIGHTS:
                axis_to_findings.setdefault(axis, []).append(finding)
    affected_axes: list[dict[str, Any]] = []
    for axis in WEIGHTS:
        linked = axis_to_findings.get(axis, [])
        if not linked:
            continue
        axis_score = clamp_score(axis_scores.get(axis, 0.0))
        weight = WEIGHTS[axis]
        affected_axes.append(
            {
                "axis": axis,
                "score": axis_score,
                "weight": weight,
                "weighted_contribution": round(axis_score * weight, 3),
                "weighted_loss_from_max": round((8.0 - axis_score) * weight, 3),
                "severity": highest_severity([str(finding.get("severity")) for finding in linked]),
                "finding_types": sorted({str(finding.get("type")) for finding in linked}),
            }
        )
    return {
        "occlusion_overlap_check": OCCLUSION_OVERLAP_CHECK,
        "scoring_rule": "rubric_weights stay fixed; occlusion lowers the affected axis_scores.",
        "rubric_weights": WEIGHTS,
        "weighted_score_from_axis_scores": round(weighted_score, 3),
        "occlusion_weighted_loss_from_max": round(sum(item["weighted_loss_from_max"] for item in affected_axes), 3),
        "affected_axes": affected_axes,
    }


def weighted_axis_score(axis_scores: dict[str, float]) -> float:
    weighted = sum(clamp_score(axis_scores.get(axis, 0.0)) * weight for axis, weight in WEIGHTS.items())
    return clamp_score(weighted)


def calibrate_axis_scores_to_total(axis_scores: dict[str, float], target_score: float) -> dict[str, float]:
    """Preserve axis differences while making their weighted total round to target_score."""
    target = clamp_score(target_score)
    adjusted = {axis: clamp_score(axis_scores.get(axis, target)) for axis in WEIGHTS}
    for _ in range(8):
        current = weighted_axis_score(adjusted)
        residual = target - current
        if abs(residual) < 0.05:
            break
        if residual > 0:
            eligible = [axis for axis, value in adjusted.items() if value < 8.0]
        else:
            eligible = [axis for axis, value in adjusted.items() if value > 0.0]
        if not eligible:
            break
        eligible_weight = sum(WEIGHTS[axis] for axis in eligible)
        if eligible_weight <= 0:
            break
        delta = residual / eligible_weight
        for axis in eligible:
            adjusted[axis] = clamp_score(adjusted[axis] + delta)
    return adjusted


def axis_scores_are_uniform(axis_scores: dict[str, float]) -> bool:
    values = [clamp_score(axis_scores.get(axis, 0.0)) for axis in WEIGHTS]
    return bool(values) and max(values) - min(values) < 0.05


def fallback_axis_scores_for_uniform_bucket(target_score: float, rationale: str) -> dict[str, float]:
    """Derive non-uniform axis scores when a bucket judge returns flat axes."""
    target = clamp_score(target_score)
    scores = {
        "visual_impact_originality": target + 0.2,
        "composition_hierarchy": target,
        "typography": target - 0.2,
        "color_material": target + 0.1,
        "detail_finish": target - 0.1,
        "basic_usability": target + 0.3,
    }
    text = rationale or ""
    if _contains_any(text, ("模板", "常见", "普通", "默认", "通用", "缺乏独特", "不够独特")):
        scores["visual_impact_originality"] -= 0.3
        scores["detail_finish"] -= 0.2
    if _contains_any(text, ("品牌", "视觉", "插画", "3D", "产品图", "记忆点", "主题")):
        scores["visual_impact_originality"] += 0.2
    if _contains_any(text, ("排版", "字体", "文字", "标题", "换行", "拥挤", "可读")):
        scores["typography"] -= 0.3
    if _contains_any(text, ("层级", "结构", "布局", "间距", "留白", "卡片")):
        scores["composition_hierarchy"] += 0.1
    if _contains_any(text, ("色", "材质", "渐变", "光影", "深色", "主题色")):
        scores["color_material"] += 0.2
    if _contains_any(text, ("粗糙", "拼装", "细节", "polish", "组件", "默认控件")):
        scores["detail_finish"] -= 0.3
    if _contains_any(text, ("遮挡", "重叠", "不可读", "操作失败", "裁切", "溢出")):
        scores["basic_usability"] -= 0.6
        scores["composition_hierarchy"] -= 0.3
    scores = {axis: clamp_score(value) for axis, value in scores.items()}
    return calibrate_axis_scores_to_total(scores, target)


def apply_blocking_occlusion_axis_penalties(
    axis_scores: dict[str, float],
    findings: list[dict[str, Any]],
) -> dict[str, float]:
    return apply_occlusion_axis_penalties(axis_scores, findings, blocking_only=True)


def apply_occlusion_axis_penalties(
    axis_scores: dict[str, float],
    findings: list[dict[str, Any]],
    *,
    blocking_only: bool = False,
) -> dict[str, float]:
    updated = dict(axis_scores)
    for finding in findings:
        severity = str(finding.get("severity") or "moderate")
        if blocking_only and severity != "blocking":
            continue
        cap = OCCLUSION_SEVERITY_AXIS_CAPS.get(severity)
        if cap is None:
            continue
        axes = finding.get("affected_axes") if isinstance(finding.get("affected_axes"), list) else []
        for axis in axes:
            if axis in updated:
                updated[axis] = min(clamp_score(updated[axis]), cap)
    return updated


def normalize_designer_review(value: Any) -> dict[str, list[str]] | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = _short_text(value, 500)
        return {"pros": [], "cons": [text] if text else [], "suggestions": []}
    if not isinstance(value, dict):
        return None
    review: dict[str, list[str]] = {}
    for key in ("pros", "cons", "suggestions"):
        items = value.get(key)
        if isinstance(items, list):
            review[key] = [_short_text(item, 240) for item in items if _short_text(item, 240)]
        elif isinstance(items, str):
            text = _short_text(items, 240)
            review[key] = [text] if text else []
        else:
            review[key] = []
    return review if any(review.values()) else None


def prompt_common_context(request: dict[str, Any]) -> tuple[str, str]:
    weight_lines = "\n".join(f"- {key}: {weight:.2f}" for key, weight in WEIGHTS.items())
    image = request.get("image") if isinstance(request.get("image"), dict) else {}
    meta = f"""
样本信息：
- viewport: {image.get("viewport")}
- screenshot_size: {image.get("width")}x{image.get("height")}
- rubric_version: {request.get("rubric_version")}

{quality_instruction_block(request)}
""".strip()
    return weight_lines, meta


def build_prompt_aesthetic_v4(request: dict[str, Any]) -> str:
    weight_lines, meta = prompt_common_context(request)
    judge_name = "aesthetic-v4"
    boundary_stabilizers = """
Boundary stabilizers:

Second-pass narrow corrections:
- Empty calorie/food logs with a goal field, one select, one quantity field, an add button,
  an empty intake list, and plain green status/progress styling are [0,10).
- Empty medication/reminder forms with a colored header, three default inputs, one action
  button, and an empty list are [0,10).
- A colorful single-card to-do toy with gradient background, progress bar, input, filter
  chips, three rows, and decorative blobs is [10,20), not [30,40).
- Local salon/barber/service pages with a dark topbar, centered text-only service cards,
  staff cards, review cards, no real imagery, and generic spacing are [10,20), not [20,30).
- Simple ticket/event catalogs with a purple hero, ordinary tabs/cards, prices, buy
  buttons, and stock or broken image cards are [20,30).
- Simple health/pet/utility logs with several fields, a list area, and basic cards are
  [20,30) when there is a complete workflow but little visual polish.
- Purple or glass countdown/event widgets with a deliberate central card, date/number
  emphasis, and coherent color treatment are [40,50) when polished.
- A long refined fit-out/interior service page with a named brand, premium navigation,
  credible project photo, two-column copy, quote/contact form, and polished CTA should
  choose [70,80) when the top designed surface is clearly launch-grade.


Additional boundary stabilizers:
- Text-only fiction/news/community portals with plain colored topbar, no real imagery,
  default white cards, simple story/date/list blocks, weak type, and large blank space
  are [0,10), even when several content blocks are visible.
- Empty multi-control tools are not all [0,10). If a page has repeated category
  sections, several inputs/selects/textareas, multiple action buttons, or four
  coordinated cards, it is usually [10,20) or [20,30), not [0,10).
- Low learning/practice pages with vocabulary/grammar/interactive sections in one card,
  or health/pet/utility logs with multiple fields plus an empty record/list area, are
  [20,30) when the workflow is complete but visually plain.
- Meeting notes, planning, checklist, or assistant tools with several repeated cards,
  empty-state placeholders, and a final generate/save action can be [30,40) when the
  product workflow is clearly organized, even if visual styling is default.
- Salon/barber/luxury service pages with one refined hero photo, gold/dark palette,
  CTA, and credible brand tone should not jump to [60,70) unless the broader component
  system is visible; common single-hero versions are [40,50).
- Clean sales/KPI/MMSE/legal/data-story dashboards with tidy cards, charts, filters,
  or side panels are often [40,50) when the component language is polished but generic.
  Do not lift them to [50,60) or [60,70) for chart presence alone.
- Rich themed dashboards such as Mars/weather, luxury checkout, dark health control
  panels, carbon comparison, or finance calculators can be [50,60) when polished, but
  keep them below [60,70) unless there is a distinctive brand system beyond dashboard
  cards, large numbers, and ordinary charts.
- Refined mobile health/habit/period/travel/reading apps should normally stay [60,70)
  when they are polished but follow a familiar app shell. Use [70,80) only for stronger
  identity or more distinctive visual assets.
- If a landing page has a large custom product/3D illustration, disciplined whitespace,
  mature navigation/CTA, and strong black/white or brand rhythm, do not misread blank
  whitespace as missing content; choose [70,80) when the hero/product system is visible.


Final exact-boundary stabilizers:
- Wrong-answer, quiz, meeting-minutes, checklist, or utility form tools with several
  selects/inputs/textareas and one or two clear actions are [10,20) or [20,30), not
  [0,10). Use [10,20) for a single plain form; use [20,30) when multiple fields imply a
  complete workflow.
- Colorful gradient/glass to-do toys with 0-count stat chips, input, filter chips, and
  an empty illustration are [20,30). The content is thin, but the visual treatment and
  control set are richer than a [10,20) default form.
- Basic health management pages with two cards, date/time/medicine/symptom inputs,
  green actions, and a resource/footer area are [20,30), even if the footer is locally
  clipped or the controls are default.
- A single physics/refraction simulator with dark themed background, visible diagram,
  one slider, angle readout, and formula text is [40,50) when the scene is coherent.
- Single-hero luxury/salon/service pages with credible photo, dark/gold palette, refined
  logo/nav/CTA, and polished headline treatment are [40,50). Do not promote them above
  [50,60) without broader service cards or brand system depth.
- Sales KPI dashboards with cream background, orange/green/yellow charts, pill filters,
  and tidy cards are [40,50) when they remain a common dashboard template.
- Dark legal/learning/literature/data dashboards with side panels, grids, stage cards,
  and simple charts are [40,50) unless the visual identity is clearly more bespoke.
- Research/community collaboration portals with hero/search/stats/category chips plus
  idea list, publish form, or recommendation panels are [50,60): stronger than a common
  landing page, but not a bespoke brand system.
- Bauhaus/editorial carbon or finance comparison pages with strong color system, aligned
  cards, and clear data hierarchy are [50,60), not [60,70), unless chart/brand depth is
  clearly exceptional.
- Mobile course/academic module lists with selected course control, progress bar, and
  disciplined repeated lesson cards can be [60,70) when typography and spacing are
  refined, even if the state is mostly empty.
- Product/crypto/payment landing pages with a large custom product/3D illustration,
  disciplined whitespace, credible brand rhythm, navigation/CTA, and partner/security
  modules are [70,80). Do not score them low just because whitespace is generous or a
  cookie banner is visible.
- Pet/health/travel/period mobile apps with overdue/status hero card, At-a-glance metrics,
  upcoming list, bottom navigation, and a prominent FAB are [70,80) when material, color,
  and spacing feel launch-grade.
"""
    return f"""
You are aesthetic-v4, a raw/direct UI screenshot judge. Judge only the attached
screenshot plus this generic rubric. Never use filenames, folders, sample ids,
source labels, designer buckets, old scores, or per-sample mappings.

Output one fixed bucket:
- [0,10) -> score 0.4
- [10,20) -> score 1.2
- [20,30) -> score 2.0
- [30,40) -> score 2.8
- [40,50) -> score 3.6
- [50,60) -> score 4.4
- [60,70) -> score 5.2
- [70,80) -> score 6.0
- [80,100] -> score 7.2

This is a generated-HTML review set. Bucket boundaries are stricter than a
normal usability review. Match designer-style aesthetic strata, not whether the
page merely works.

Hard boundary overrides have precedence over general impression:
- Random picker / roulette / "what to eat" toy utilities with one colorful wheel
  or central graphic, default input, default buttons, rough removable list rows,
  and large blank space are [0,10). Do not promote them to [20,30) for having a
  colorful graphic or a complete function.
- Sparse API/admin pages with a dark/plain topbar, three default white cards,
  ordinary input fields, blue buttons, and large blank space are [10,20).
- Very light consumer banking/account pages with a simple topbar, only three
  default cards, a balance/readout, green buttons, short transaction list, and
  little financial component depth are [20,30), not [10,20) and not [30,40).
- Blue consumer banking dashboards with account balance, quick actions, and
  transaction list are [30,40) when component language remains generic.
- Dark wallet/finance dashboards with sidebar, balance card, credit-card mockup,
  quick actions, one simple trend chart, and transaction list are [40,50), not
  [70,80), unless there is a clearly bespoke brand system and richer state
  design beyond common fintech templates.
- Dark SaaS/API dashboards with sidebar, KPI cards, charts, tables, status
  badges, and consistent spacing are [50,60) when polished but common.
- Polished mobile/feed shells with illustration cards, tags, bottom navigation,
  and floating actions are [60,70) unless the brand/product direction is much
  more distinctive than a common feed.
- Refined crypto/payment/product landing pages with custom 3D/product imagery,
  disciplined black/white rhythm, strong CTA, and credible brand modules can be
  [70,80).

Low-end boundaries:
- [0,10): failed or near-failed visual quality. Use for bare toy utilities,
  practice apps, empty logs, single-action forms, rough content portals, or pages
  dominated by default controls, blank space, weak proportions, rough list rows,
  system typography, and no real visual system.
- [10,20): low-quality demo/template. Function is visible and layout is stable,
  but the page is mainly default cards, default form controls, ordinary buttons,
  generic topbars, simple lists/tables, sparse content, or template shell.
- [20,30): low but complete. There is more structure than a sparse demo:
  checkout/event/ticket listings, simple health/pet/utility logs, basic learning
  workflows, or classroom simulators. Still default-heavy, weakly themed, and
  not product-grade.
- [30,40): below-average ordinary product UI. Complete and readable with
  multi-section layout or card/list/table structure, but generic visual language,
  limited polish, and little theme or brand specificity.

Middle/high boundaries:
- [40,50): ordinary designed UI. Coherent simulators, common finance/wallet
  pages, simple photo-hero landing pages, clinical/professional calculators,
  note/workspace tools, and template-like dashboards when organized and visually
  intentional but not truly premium.
- [50,60): good UI. Dense professional dashboards, planning/workflow tools, or
  refined branded/product pages with consistent component systems and visible
  polish, still not strongly memorable or bespoke.
- [60,70): high quality but not elite. Use for polished mobile trackers, task
  apps, inboxes, calendars, habit dashboards, editorial/zine pages, minimal
  commerce/gallery pages, or participatory dashboards with mature hierarchy and
  material but familiar IA.
- [70,80): excellent/production-grade. Use only when the screen has stronger
  product/brand direction, refined type, mature spacing/material, distinctive
  visual identity, credible imagery/assets, polished CTA/navigation/components,
  and launch-grade finish.
- [80,100]: almost never use; reserve for exceptional design-site quality.

Full-page exact-boundary corrections:
- Direct long screenshot mode: if the attached image is very tall, treat it as
  a full-page screenshot. Judge the first viewport/top screen as the primary
  aesthetic signal, then use lower content only to check consistency, product
  depth, repetition, responsive behavior, and rendering defects.
- Mobile fixed bottom navigation/tab bars/safe-area chrome are normal app
  structure. Do not mark them as defects unless they hide essential text,
  primary actions, or key data with no visible recovery space.
- Separate [0,10) from [10,20) by state richness. A bare one-card utility with
  one input/button and empty space is [0,10); a low template with several
  controls, filter chips, dropdowns, list/table rows, or a stable page header is
  usually [10,20) even if ugly.
- Simple ticket/table business pages with a plain topbar, small table/list, and
  buy/action buttons remain [10,20) when almost all styling is default. A
  gradient hero or broken/placeholder image cards does not lift them above
  [20,30).
- Colorful/glassy single-card toy tools with counters, filters, input, and an
  empty list can be [20,30) only when the visual treatment is deliberate; do not
  collapse every empty toy to [0,10).
- Generic photo-hero research/community/service pages with stock-like imagery,
  ordinary nav, centered CTA, and basic feature cards are [30,40) unless the
  brand/photo treatment is clearly premium.
- Dark data-story cards, KPI dashboards, clinical calculators, and common sales
  analytics pages that look polished but template-like should stay [40,50)
  unless they show richer state design or stronger product depth.
- A single-card simulator with a coherent visual scene, themed background, and
  clear slider/readout should be [40,50), not [20,30), when the scene is visibly
  designed.
- Multi-panel planning/workflow tools and dark calculation dashboards with
  strong typography, organized card grids, and professional spacing can be
  [50,60) even if controls are ordinary.
- Polished but common mobile trackers, task apps, inboxes, calendars, and habit
  dashboards with bottom navigation, cards, progress states, and refined spacing
  are usually [60,70), not [70,80), when they lack a distinctive brand/art system.
- Editorial/zine pages with strong typography, image treatment, and playful
  print-inspired details are [60,70) when memorable but still a conventional
  content portal.
- Participatory/community dashboards with strong brand color, metrics strip,
  proposal cards, voting/ranking modules, and consistent spacing can be [60,70).
- Minimal commerce/product/gallery pages with dominant product photography,
  sparse navigation, disciplined whitespace, and restrained typography can be
  [60,70); do not score them low merely because there are few controls.
- Keep [70,80) for genuinely launch-grade screens: refined mobile health/pet/
  travel/academic/onboarding apps or brand/product sites with stronger material
  treatment, more distinctive identity, and cleaner component finish than a
  common app shell.

Narrow UI-pattern boundary rules:
- Use these only when the visual evidence closely matches the UI pattern; do not
  generalize them to every sparse, mobile, or long page.
- A centered login/search/one-question form, blank gradient single-action panel,
  or tiny default form with almost no content is [0,10), not [10,20).
- A sparse to-do/task row with clear title, input/select, one action button, and
  divider/list area is [10,20), not [0,10). A generic form with only labels,
  inputs, and a button stays [10,20), not [20,30).
- Event/ticket catalogs with gradient hero, ordinary tabs/cards, prices, buy
  buttons, and stock/broken image cards are [20,30).
- Classroom refraction/angle/math simulators with one white card, one diagram,
  one slider, and formula/readout text are [20,30), unless there are multiple
  coordinated panels or mature product chrome.
- Generic research/community/service landing pages with blue navigation, gray or
  stock-like hero treatment, simple feature cards, plain story rows, and a basic
  contact form are [30,40), not [40,50).
- Note/editor/learning workspaces with left sidebar, active edit panel, tags,
  and save/delete actions are [40,50) even when controls are plain.
- Light sales/KPI dashboards and dark narrative/data dashboards with a few chart
  cards and template-like layout are [40,50); do not lift them for charts, dark
  theme, or a big headline alone.
- Professional skill/planning/assessment/roadmap workspaces with structured
  panels, recommendations, stats, filters, and restrained typography are
  [50,60) even in empty state.
- Common mobile job/application trackers with warm cards, large list items,
  bottom navigation, and floating add button are [50,60), not [60,70).
- Dense mobile operational inbox/notification/task/calendar/status apps with
  mature type, hierarchy, readable list cards, bottom navigation, and polished
  states are [60,70), unless the brand direction is visibly launch-grade.
- Minimal workshop/craft/project-library pages with restrained editorial type,
  material palette, whitespace, project cards, chips, and credible imagery are
  [60,70), not low utility UI.
- Refined mobile health/pet/travel/academic/route/onboarding apps with mature
  color, cards, bottom navigation, visual identity, and launch-grade spacing are
  [70,80). Bottom nav or tall capture does not demote.
- Long B2B service/product/fit-out pages with refined navigation, custom
  imagery, polished CTA/form, and coherent brand tone can be [70,80) when the
  first viewport is launch-grade.

{boundary_stabilizers}

ZERO_DEFECT:
- If core text, tables, key data, or primary controls are unreadable because of
  overlap, clipping, overflow, broken responsive layout, or real occlusion,
  choose a low bucket and explain the defect. Normal mobile bottom nav alone is
  not a defect.

If uncertain between adjacent buckets:
- choose lower for [0,10) vs [10,20), [10,20) vs [20,30), and [60,70) vs [70,80)
  unless the higher bucket evidence is explicit.
- choose the bucket matching the UI-pattern boundary, not a neutral midpoint.

Observation weights, for reasoning only:
{weight_lines}

Output requirements:
- score must be exactly one fixed score above.
- all six axis_scores must equal score.
- rationale must be 100-170 Chinese chars, naming bucket, UI pattern, visible
  evidence, and why the adjacent higher bucket is not reached.
- rationale must not mention implementation details, model names, source labels,
  or boundary stabilizer names.

Return JSON only:
{{
  "bucket": "[0,10)",
  "score": 0.4,
  "axis_scores": {{
    "visual_impact_originality": 0.4,
    "composition_hierarchy": 0.4,
    "typography": 0.4,
    "color_material": 0.4,
    "detail_finish": 0.4,
    "basic_usability": 0.4
  }},
  "rationale": "命中 [x,y) 档：属于...类型；可见证据是...；未进更高档因为...",
  "backend_meta": {{
    "judge": "{judge_name}",
    "rubric_version": "{request.get('rubric_version')}",
    "score_scale": "0-8"
  }}
}}

{meta}
""".strip()


def build_prompt(request: dict[str, Any], prompt_version: str) -> str:
    if prompt_version in {
        "aesthetic-v4",
        "aesthetic_v4",
    }:
        return build_prompt_aesthetic_v4(request)
    raise ValueError(
        "unsupported prompt version for this package: "
        f"{prompt_version}; use aesthetic-v4"
    )
