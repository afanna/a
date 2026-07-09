from __future__ import annotations

from typing import Any


METRIC_LABELS: dict[tuple[str, str], str] = {
    ("information", "coverage"): "信息覆盖率",
    ("information", "truncation"): "文字截断风险",
    ("information", "duplicate"): "重复文字",
    ("layout", "whitespace"): "留白比例",
    ("layout", "margin_consistency"): "边距一致性",
    ("layout", "spacing_rhythm"): "间距节奏",
    ("layout", "density"): "元素密度",
    ("layout", "overlap"): "元素重叠",
    ("layout", "overflow"): "元素溢出",
    ("visual", "color_harmony"): "色彩协调",
    ("visual", "contrast"): "文字对比度",
    ("visual", "visual_focus"): "视觉焦点",
    ("visual", "visual_balance"): "视觉平衡",
    ("visual", "text_image_ratio"): "图文比例",
    ("visual", "reading_flow"): "阅读路径",
    ("visual", "hierarchy"): "视觉层级",
    ("consistency", "alignment"): "对齐一致性",
    ("consistency", "typography_rhythm"): "字号节奏",
    ("consistency", "component_size"): "组件尺寸一致性",
    ("consistency", "corner_radius_consistency"): "圆角一致性",
    ("consistency", "padding_consistency"): "内边距一致性",
    ("consistency", "icon_size_consistency"): "图标尺寸一致性",
    ("consistency", "grid"): "网格一致性",
    ("consistency", "style_simplicity"): "风格简洁度",
}


FIELD_LABELS: dict[str, str] = {
    "avg_lab_distance": "平均色差",
    "backtracks": "阅读回退次数",
    "color_count": "主色数量",
    "component_count": "组件数量",
    "gap_count": "间距样本数",
    "icon_count": "图标数量",
    "iou": "重叠率",
    "left": "左侧元素",
    "low_confidence_texts": "低置信度文字",
    "matched": "已匹配文字",
    "missing": "缺失文字",
    "padding_values": "内边距样本",
    "path_norm": "阅读路径长度",
    "proportions": "颜色占比",
    "radii": "圆角样本",
    "ratios": "对比度样本",
    "required_count": "必要文字数量",
    "right": "右侧元素",
    "sizes": "尺寸样本",
    "truncated": "疑似截断文字",
    "unique_radius_count": "圆角档位数量",
}


METRIC_DESCRIPTIONS: dict[tuple[str, str], str] = {
    ("information", "coverage"): "信息覆盖率是指 DSL 中要求展示的必要文字，在截图中被完整识别出来的程度。",
    ("information", "truncation"): "文字截断风险是指必要文字是否出现显示不完整、被省略或识别置信度较低的问题。",
    ("information", "duplicate"): "重复文字是指截图中是否存在语义高度相似的重复文本，避免信息冗余影响阅读。",
    ("layout", "whitespace"): "留白比例是指卡片中未被内容占用的空间是否适中，帮助内容呼吸并提升可读性。",
    ("layout", "margin_consistency"): "边距一致性是指内容与卡片边界之间的距离是否稳定，避免视觉边界松散或拥挤。",
    ("layout", "spacing_rhythm"): "间距节奏是指元素之间的垂直间隔是否有规律，让信息组织更清晰。",
    ("layout", "density"): "元素密度是指卡片内文字、图标和组件的占用程度是否适中，避免过空或过挤。",
    ("layout", "overlap"): "元素重叠是指不同视觉元素之间是否互相遮挡，影响信息识别和界面整洁度。",
    ("layout", "overflow"): "元素溢出是指视觉元素是否超出卡片边界，影响卡片完整性和渲染稳定性。",
    ("visual", "color_harmony"): "色彩协调是指通过合理的颜色组合，创造出视觉上和谐、统一的效果。",
    ("visual", "contrast"): "文字对比度是指文字与背景之间是否有足够差异，保证内容清晰可读。",
    ("visual", "visual_focus"): "视觉焦点是指画面是否有明确的主次中心，让用户能快速看到最重要的信息。",
    ("visual", "visual_balance"): "视觉平衡是指主要视觉重量在卡片中的分布是否稳定，避免画面明显偏向某一侧。",
    ("visual", "text_image_ratio"): "图文比例是指文字内容与图形元素的面积关系是否协调，避免一方压过另一方。",
    ("visual", "reading_flow"): "阅读路径是指文字的阅读顺序是否顺畅，减少视线跳跃和回退。",
    ("visual", "hierarchy"): "视觉层级是指标题、重点信息和辅助信息之间是否有清晰的强弱区分。",
    ("consistency", "alignment"): "对齐一致性是指元素边缘和中心线是否形成统一秩序，提升界面整洁感。",
    ("consistency", "typography_rhythm"): "字号节奏是指字号层级数量是否稳定，避免字体大小混乱或层级不清。",
    ("consistency", "component_size"): "组件尺寸一致性是指同类视觉组件的大小是否协调，减少突兀感。",
    ("consistency", "corner_radius_consistency"): "圆角一致性是指卡片内圆角风格是否统一，避免组件形态割裂。",
    ("consistency", "padding_consistency"): "内边距一致性是指文字与其容器边界之间的空间是否稳定，保证组件观感统一。",
    ("consistency", "icon_size_consistency"): "图标尺寸一致性是指多个图标的视觉大小是否统一，避免图标抢占或弱化信息。",
    ("consistency", "grid"): "网格一致性是指元素位置是否落在稳定的横纵秩序中，提升布局规整度。",
    ("consistency", "style_simplicity"): "风格简洁度是指主色和装饰复杂度是否克制，避免视觉噪声过多。",
}


REASON_LABELS: dict[str, str] = {
    "fewer than 2 detected components": "检测到的组件少于 2 个",
    "fewer than 2 detected icons": "检测到的图标少于 2 个",
    "fewer than 2 radius samples": "可用圆角样本少于 2 个",
    "fewer than 2 vertical gaps": "可用垂直间距样本少于 2 个",
    "fewer than 2 visual elements": "检测到的视觉元素少于 2 个",
    "no component text padding samples": "没有可估算文字内边距的组件",
    "no DSL required display text found": "DSL 中没有提取到必要展示文字",
    "no OCR text found": "截图中没有识别到文字",
    "no visual elements found": "截图中没有检测到视觉元素",
}


VALUE_LABELS: dict[str, str] = {
    ">=1 element": "至少 1 个元素",
    ">=2 components": "至少 2 个组件",
    ">=2 elements": "至少 2 个元素",
    ">=2 gaps": "至少 2 个间距样本",
    ">=2 icons": "至少 2 个图标",
    ">=2 radius samples": "至少 2 个圆角样本",
    ">=3 text blocks": "至少 3 个文字块",
    "low": "越低越好",
}


def metric_label(dimension: str, name: str) -> str:
    return METRIC_LABELS.get((dimension, name), name.replace("_", " "))


def metric_description(dimension: str, name: str) -> str:
    return METRIC_DESCRIPTIONS.get((dimension, name), "该指标用于衡量卡片在对应维度上的表现。")


def reason_label(reason: Any) -> str:
    text = str(reason or "")
    return REASON_LABELS.get(text, text)


def format_value(value: Any) -> str:
    if value is None:
        return "无"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, str):
        return VALUE_LABELS.get(value, reason_label(value))
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, dict):
        if not value:
            return "无"
        return "；".join(f"{field_label(key)}：{format_value(item)}" for key, item in value.items())
    if isinstance(value, (list, tuple)):
        if not value:
            return "无"
        return "、".join(format_value(item) for item in value)
    return str(value)


def field_label(name: Any) -> str:
    text = str(name)
    return FIELD_LABELS.get(text, text.replace("_", " "))
