from __future__ import annotations

from typing import Any

from .math_utils import clamp
from .models import Deduction, MetricResult


TEMPLATES: dict[str, dict[str, str]] = {
    "geometry.density_too_high": {
        "reason": "DSL 几何信息密度过高，卡片容易显得拥挤。",
        "fix_hint": "减少次要组件或扩大关键组件之间的间距，避免多个信息块挤在同一视觉区域。",
        "prompt_hint": "生成卡片时控制信息密度，主标题、核心数值和辅助信息之间保留清晰留白。",
    },
    "geometry.density_too_low": {
        "reason": "DSL 几何信息密度偏低，卡片可能显得空。",
        "fix_hint": "适当放大主视觉或补充一个有价值的辅助信息区。",
        "prompt_hint": "生成极简卡片时仍要保证主视觉或核心信息有足够存在感，避免画面过空。",
    },
    "geometry.edge_too_close": {
        "reason": "主要元素距离卡片边缘过近。",
        "fix_hint": "增加安全边距，主要内容距离边缘建议不少于 8-12vp。",
        "prompt_hint": "生成卡片时为主标题、核心数值、图标和按钮保留安全边距，避免贴边。",
    },
    "geometry.alignment_weak": {
        "reason": "DSL 组件对齐关系较弱，视觉秩序不足。",
        "fix_hint": "让同组文本和图标共享左边缘、中心线或明确的网格线。",
        "prompt_hint": "生成布局时让同一信息组使用统一左对齐或中心对齐，不要让元素随机漂移。",
    },
    "geometry.grid_weak": {
        "reason": "DSL 组件未明显吸附到稳定隐式网格。",
        "fix_hint": "优先使用 4/8/12/16vp 的间距和尺寸节奏。",
        "prompt_hint": "生成卡片时使用稳定的 4/8/12/16vp 间距系统，减少零散坐标和尺寸。",
    },
    "geometry.overlap": {
        "reason": "DSL 几何估算发现组件存在重叠风险。",
        "fix_hint": "调整重叠组件的位置、尺寸或父容器布局，确保主内容互不遮挡。",
        "prompt_hint": "生成 DSL 时检查所有主要文本、图标、按钮的 bbox，不允许主内容互相重叠。",
    },
    "geometry.rhythm_weak": {
        "reason": "组件间距节奏不稳定，信息组之间忽紧忽松。",
        "fix_hint": "统一相邻信息块之间的垂直 gap，让阅读节奏更平稳。",
        "prompt_hint": "生成卡片时让同层级信息块使用一致间距，避免有的很近、有的过远。",
    },
    "geometry.hierarchy_weak": {
        "reason": "DSL 字号层级不明显，主次关系不足。",
        "fix_hint": "拉开标题、核心数值和辅助文字的字号或字重差异。",
        "prompt_hint": "生成卡片时建立清晰字号层级：核心数值最大，标题次之，辅助说明更小。",
    },
    "geometry.typography_too_fragmented": {
        "reason": "DSL 字号层级过多，字体节奏显得零散。",
        "fix_hint": "减少字号档位，服务卡片通常控制在 2-4 个字号层级。",
        "prompt_hint": "生成卡片时限制字号档位，避免每个文本都使用不同字号。",
    },
    "information.text_missing": {
        "reason": "截图 OCR 没有找到 DSL 期望展示的文字证据。",
        "fix_hint": "检查该文本是否字号过小、被遮挡、被裁切或颜色对比不足。",
        "prompt_hint": "生成卡片时确保所有核心文本真实可见，不被装饰、图片或容器裁切遮挡。",
    },
    "information.number_mismatch": {
        "reason": "截图 OCR 没有匹配到 DSL 期望展示的关键数字。",
        "fix_hint": "检查核心数值是否完整显示，避免被截断、缩小或替换。",
        "prompt_hint": "生成卡片时保证温度、金额、百分比、时间等关键数字完整显示。",
    },
    "information.unit_weak_match": {
        "reason": "核心数字已匹配，但单位符号的截图证据不足。",
        "fix_hint": "放大单位符号或让单位与数字处于同一文本组件中，避免单位过小或被裁切。",
        "prompt_hint": "生成卡片时温度、百分比、金额等数值必须保留数字和单位，例如 25℃ 不要只显示 25。",
    },
    "visual.low_contrast": {
        "reason": "截图中文本与背景对比不足，影响可读性。",
        "fix_hint": "提高文字颜色和背景之间的明度差，浅色背景避免使用浅灰小字。",
        "prompt_hint": "生成卡片时避免低对比文字，正文和关键数值要有清晰可读的前景/背景对比。",
    },
    "visual.palette_fragmented": {
        "reason": "截图主色关系不够稳定，颜色显得零散。",
        "fix_hint": "减少无关色彩，围绕主色、辅助色和强调色建立配色。",
        "prompt_hint": "生成卡片时控制颜色数量，使用稳定主色和少量强调色，不要堆叠过多色相。",
    },
    "visual.balance_off_center": {
        "reason": "截图视觉重心偏移较明显。",
        "fix_hint": "调整主视觉、文本组和按钮的位置，让画面重量更均衡。",
        "prompt_hint": "生成卡片时注意视觉重心，主视觉和文字组要形成稳定平衡。",
    },
    "visual.focus_unclear": {
        "reason": "截图视觉焦点不清晰，第一眼不容易看到核心信息。",
        "fix_hint": "突出核心数值或标题，弱化背景和次要装饰。",
        "prompt_hint": "生成卡片时明确一个主焦点，避免背景、图标和多个文本同时抢注意力。",
    },
    "visual.text_image_balance": {
        "reason": "截图图文比例失衡，文字、图片或装饰之间的视觉占比不协调。",
        "fix_hint": "调整文本组、图标和背景装饰的占比，让核心内容与视觉元素形成稳定配合。",
        "prompt_hint": "生成卡片时控制图文比例，避免只有文字堆叠或装饰压过核心信息。",
    },
    "visual.reading_flow_weak": {
        "reason": "截图阅读路径不够顺畅，视线跳转成本偏高。",
        "fix_hint": "按从主标题到核心数值再到辅助信息的顺序组织文本，减少跨区域跳读。",
        "prompt_hint": "生成卡片时让阅读顺序清晰连贯，主信息、辅助信息和操作区依次展开。",
    },
    "layout.margin_weak": {
        "reason": "截图边距关系不稳定，画面边界显得松散或拥挤。",
        "fix_hint": "统一主要内容与卡片边缘的距离，避免某一侧过紧或过松。",
        "prompt_hint": "生成卡片时保持稳定安全边距，让主内容与卡片边界形成清晰秩序。",
    },
    "layout.rhythm_weak": {
        "reason": "截图中组件间距节奏不稳定，模块组织显得生硬。",
        "fix_hint": "统一同层级模块之间的间距，必要时减少硬分割色块，改用留白分组。",
        "prompt_hint": "生成卡片时用一致间距组织模块，减少生硬分割，让信息组有呼吸感。",
    },
    "layout.overlap": {
        "reason": "截图检测到元素重叠风险。",
        "fix_hint": "根据真实渲染结果调整组件位置或尺寸，避免内容遮挡。",
        "prompt_hint": "生成卡片时预留渲染余量，避免文本和图标在截图中重叠。",
    },
    "layout.overflow": {
        "reason": "截图检测到元素溢出卡片区域。",
        "fix_hint": "缩小或移动越界组件，确保所有主内容位于卡片安全区域内。",
        "prompt_hint": "生成卡片时所有主要元素必须位于卡片边界内，并保留安全边距。",
    },
}


GENERIC_METRIC_CODES: dict[tuple[str, str], str] = {
    ("visual", "contrast"): "visual.low_contrast",
    ("visual", "color_harmony"): "visual.palette_fragmented",
    ("visual", "visual_balance"): "visual.balance_off_center",
    ("visual", "visual_focus"): "visual.focus_unclear",
    ("visual", "text_image_ratio"): "visual.text_image_balance",
    ("visual", "reading_flow"): "visual.reading_flow_weak",
    ("layout", "margin_consistency"): "layout.margin_weak",
    ("layout", "spacing_rhythm"): "layout.rhythm_weak",
    ("layout", "overlap"): "layout.overlap",
    ("layout", "overflow"): "layout.overflow",
}


HARD_CAPS: dict[str, float] = {
    "geometry.overlap": 65.0,
    "information.number_mismatch": 70.0,
    "information.text_missing": 74.0,
    "visual.low_contrast": 74.0,
    "layout.overlap": 70.0,
    "layout.overflow": 70.0,
}


# 递进式硬封顶（P0）：cap = base_cap - slope * magnitude，取整到 0.5，下限 CAP_FLOOR。
# magnitude 为 None 的扣分回退到 HARD_CAPS 固定基础封顶值。
# 斜率经 50 样本网格搜索标定（after2，允许范围 [8, 24]）：
# - text_missing 陡（24）：文本缺失率与教师分方向一致，信号可靠。
# - low_contrast 缓（8）：单块最小对比度噪声大（小字注释常见），陡斜率会误伤教师高分卡。
# - geometry.overlap 较陡（20）：DSL 重叠幅度带有一定教师信号。
CAP_SLOPES: dict[str, float] = {
    "information.text_missing": 24.0,
    "visual.low_contrast": 8.0,
    "information.number_mismatch": 8.0,
    "geometry.overlap": 20.0,
    "layout.overlap": 8.0,
    "layout.overflow": 8.0,
}
CAP_FLOOR: float = 40.0


def collect_deductions(metrics: list[MetricResult]) -> list[Deduction]:
    records: list[Deduction] = []
    for metric in metrics:
        for raw in metric.details.get("deductions", []) if isinstance(metric.details, dict) else []:
            if isinstance(raw, dict):
                records.append(enrich_deduction(raw, metric))
        generic_code = GENERIC_METRIC_CODES.get((metric.dimension, metric.name))
        if generic_code and metric.score is not None and metric.score < 65:
            records.append(
                enrich_deduction(
                    {
                        "code": generic_code,
                        "source": "screenshot",
                        "severity": "medium" if metric.score < 50 else "low",
                        "score_delta": -round((65 - float(metric.score)) / 4, 2),
                        "evidence": f"{metric.dimension}.{metric.name} score={metric.score:.2f}, value={metric.value}",
                        "magnitude": generic_magnitude(generic_code, metric),
                    },
                    metric,
                )
            )
    return merge_duplicate_deductions(records)


def generic_magnitude(code: str, metric: MetricResult) -> float | None:
    """GENERIC_METRIC_CODES 通用扣分项的问题幅度（0..1，越大越糟）。

    默认按指标分距 65 分触发线的相对偏离估算：clamp((65 - score) / 65, 0, 1)。
    个别指标改用已直接计算的偏差，语义更准确：
    - visual.low_contrast：clamp(1 - min_contrast / target, 0, 1)，
      即 deviation / ideal（deviation = max(0, target - min_contrast)）。
    - layout.overlap：clamp(max_iou / 0.25, 0, 1)。
    - layout.overflow：clamp(越界面积占比, 0, 1)（本身即 0..1 比率）。
    """
    if metric.score is None:
        return None
    if code == "visual.low_contrast" and isinstance(metric.ideal, (int, float)) and float(metric.ideal) > 0:
        return clamp(float(metric.deviation or 0.0) / float(metric.ideal), 0.0, 1.0)
    if code == "layout.overlap" and isinstance(metric.value, (int, float)):
        return clamp(float(metric.value) / 0.25, 0.0, 1.0)
    if code == "layout.overflow" and isinstance(metric.value, (int, float)):
        return clamp(float(metric.value), 0.0, 1.0)
    return clamp((65.0 - float(metric.score)) / 65.0, 0.0, 1.0)


def enrich_deduction(raw: dict[str, Any], metric: MetricResult) -> Deduction:
    code = str(raw.get("code") or f"{metric.dimension}.{metric.name}")
    template = TEMPLATES.get(code, {})
    magnitude = raw.get("magnitude")
    return Deduction(
        code=code,
        source=str(raw.get("source") or metric.dimension),
        severity=str(raw.get("severity") or "low"),
        score_delta=float(raw.get("score_delta") or 0.0),
        reason=str(raw.get("reason") or template.get("reason") or code),
        evidence=str(raw.get("evidence") or ""),
        component_ids=[str(item) for item in raw.get("component_ids", []) if item is not None]
        if isinstance(raw.get("component_ids", []), list)
        else [],
        fix_hint=str(raw.get("fix_hint") or template.get("fix_hint") or ""),
        prompt_hint=str(raw.get("prompt_hint") or template.get("prompt_hint") or ""),
        magnitude=float(magnitude) if magnitude is not None else None,
    )


def merge_duplicate_deductions(records: list[Deduction]) -> list[Deduction]:
    merged: dict[tuple[str, str], Deduction] = {}
    for item in records:
        key = (item.code, item.evidence)
        existing = merged.get(key)
        if existing is None or abs(item.score_delta) > abs(existing.score_delta):
            merged[key] = item
    severity_order = {"high": 0, "medium": 1, "low": 2}
    return sorted(merged.values(), key=lambda item: (severity_order.get(item.severity, 3), item.score_delta))


def hard_caps_for(deductions: list[Deduction]) -> list[dict[str, Any]]:
    caps: list[dict[str, Any]] = []
    code_counts: dict[str, int] = {}
    for item in deductions:
        code_counts[item.code] = code_counts.get(item.code, 0) + 1
    for item in deductions:
        cap = cap_for(item, code_counts)
        if cap is None:
            continue
        if item.severity == "low" and item.code not in {"visual.low_contrast"}:
            continue
        caps.append(
            {
                "code": item.code,
                "cap": cap,
                "magnitude": item.magnitude,
                "reason": item.reason,
                "evidence": item.evidence,
            }
        )
    return sorted(caps, key=lambda item: float(item["cap"]))


def cap_for(item: Deduction, code_counts: dict[str, int]) -> float | None:
    """递进式硬封顶：cap = base_cap[code] - slope[code] * magnitude。

    - magnitude 缺失（None）时回退到 HARD_CAPS 固定基础封顶值（旧行为）。
    - 结果取整到最近的 0.5，并以 CAP_FLOOR（40）为下限。
    - 低严重度不封顶的规则不变（visual.low_contrast 特例除外），见 hard_caps_for。
    """
    base = HARD_CAPS.get(item.code)
    if base is None:
        return None
    if item.magnitude is None:
        return base
    slope = CAP_SLOPES.get(item.code, 0.0)
    raw = base - slope * clamp(float(item.magnitude), 0.0, 1.0)
    return max(CAP_FLOOR, round(raw * 2) / 2)


def prompt_suggestions_for(deductions: list[Deduction], limit: int = 8) -> list[str]:
    suggestions: list[str] = []
    seen: set[str] = set()
    for item in deductions:
        hint = item.prompt_hint.strip()
        if not hint or hint in seen:
            continue
        seen.add(hint)
        suggestions.append(hint)
        if len(suggestions) >= limit:
            break
    return suggestions
