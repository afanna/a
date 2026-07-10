#!/usr/bin/env python3
"""Shared aesthetic-v4 scoring contract.

This module is the single source for rubric axes, weights, scale conversion,
view naming, and clean JSON weighted axis rows.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any


SCORE_MIN = 0.0
SCORE_MAX = 8.0
SCORE_SCALE = {"min": SCORE_MIN, "max": SCORE_MAX, "precision": 1}
RUBRIC_VERSION = "aesthetic_static_v1"
AESTHETIC_PROFILE = "aesthetic_v4"


AXES: list[dict[str, Any]] = [
    {
        "id": "visual_impact_originality",
        "display_id": "A1",
        "name": "视觉冲击 / 原创性",
        "weight": 0.30,
        "weight_percent": 30,
        "desc": "评估页面是否有第一眼的视觉记忆点、明确的主题气质和非模板化表达。重点看是否存在强中心视觉、稳定氛围、原创构图、品牌化或题材化视觉语言，而不是只依赖常见渐变、圆角卡片、玻璃态、emoji、默认插图或普通组件堆叠。",
        "score_rule_8": "0-2: 默认模板、课堂 demo、普通表单/卡片堆叠，几乎没有视觉记忆点。\n2-4: 页面完整但常见，主要靠通用渐变、卡片、按钮、图标维持观感，原创性弱。\n4-6: 有明确主题和一定视觉焦点，整体比模板更完整，但冲击力、原创资产或品牌化仍有限。\n6-8: 有强中心视觉、稳定氛围、原创表达和高辨识度，能明显区别于普通 AI 生成页面。",
        "score_rule_100": "0-25: 默认模板、课堂 demo、普通表单/卡片堆叠，几乎没有视觉记忆点。25-50: 页面完整但常见，主要靠通用渐变、卡片、按钮、图标维持观感，原创性弱。50-75: 有明确主题和一定视觉焦点，整体比模板更完整，但冲击力、原创资产或品牌化仍有限。75-100: 有强中心视觉、稳定氛围、原创表达和高辨识度，能明显区别于普通 AI 生成页面。",
        "hard_fail": False,
    },
    {
        "id": "composition_hierarchy",
        "display_id": "A2",
        "name": "构图层级",
        "weight": 0.20,
        "weight_percent": 20,
        "desc": "评估页面的信息组织、视觉重心、空间节奏和阅读路径。重点看首屏是否有清晰主次关系，核心内容是否被正确突出，导航、内容、操作区是否有稳定分组，而不是所有卡片、标签、颜色和按钮都在抢注意力。",
        "score_rule_8": "0-2: 布局混乱、层级缺失、核心内容难以定位，或大面积空洞/拥挤导致页面像未完成原型。\n2-4: 基本能读，但主次关系弱，常见卡片网格或 dashboard 拼装感明显。\n4-6: 结构清楚，有较自然的阅读路径和视觉重心，但构图仍偏安全或缺少张力。\n6-8: 构图成熟，首屏焦点强，内容分组、留白、比例和节奏共同服务主题表达。",
        "score_rule_100": "0-25: 布局混乱、层级缺失、核心内容难以定位，或大面积空洞/拥挤导致页面像未完成原型。25-50: 基本能读，但主次关系弱，常见卡片网格或 dashboard 拼装感明显。50-75: 结构清楚，有较自然的阅读路径和视觉重心，但构图仍偏安全或缺少张力。75-100: 构图成熟，首屏焦点强，内容分组、留白、比例和节奏共同服务主题表达。",
        "hard_fail": False,
    },
    {
        "id": "typography",
        "display_id": "A3",
        "name": "字体表现",
        "weight": 0.15,
        "weight_percent": 15,
        "desc": "评估字体选择、字号层级、字重、行高、对齐和文本排版是否形成稳定系统。重点看标题、正文、标签、按钮、数字信息是否有清晰层级，字体是否匹配产品气质，文本是否可读且不拥挤。",
        "score_rule_8": "0-2: 系统默认字体痕迹强，字号/字重混乱，文本拥挤、错位、重叠或可读性差。\n2-4: 字体基本可读，但层级普通，标题、正文、标签缺少精细排版规则。\n4-6: 字体层级稳定，排版较干净，能支撑页面气质，但缺少更强的字体个性或细节控制。\n6-8: 字体选择、尺度、字重、行距和对齐高度统一，明显增强品牌感和完成度。",
        "score_rule_100": "0-25: 系统默认字体痕迹强，字号/字重混乱，文本拥挤、错位、重叠或可读性差。25-50: 字体基本可读，但层级普通，标题、正文、标签缺少精细排版规则。50-75: 字体层级稳定，排版较干净，能支撑页面气质，但缺少更强的字体个性或细节控制。75-100: 字体选择、尺度、字重、行距和对齐高度统一，明显增强品牌感和完成度。",
        "hard_fail": False,
    },
    {
        "id": "color_material",
        "display_id": "A4",
        "name": "色彩与材质",
        "weight": 0.15,
        "weight_percent": 15,
        "desc": "评估配色、明暗关系、材质质感、光影、边框、阴影和背景处理是否统一且服务主题。重点看颜色是否有优先级，材质是否精修，是否避免廉价渐变、彩虹色堆叠、无意义玻璃态或默认灰白卡片。",
        "score_rule_8": "0-2: 配色随意或极度默认，材质粗糙，颜色互相抢夺注意力或整体像未设计。\n2-4: 有基础配色但比较常见，主要依赖默认白卡、普通阴影、弱渐变或单调色块。\n4-6: 色彩关系稳定，材质和光影有一定完成度，能配合主题但不够精细或独特。\n6-8: 色彩系统成熟，材质、光影、背景和组件质感统一，形成强烈且克制的视觉氛围。",
        "score_rule_100": "0-25: 配色随意或极度默认，材质粗糙，颜色互相抢夺注意力或整体像未设计。25-50: 有基础配色但比较常见，主要依赖默认白卡、普通阴影、弱渐变或单调色块。50-75: 色彩关系稳定，材质和光影有一定完成度，能配合主题但不够精细或独特。75-100: 色彩系统成熟，材质、光影、背景和组件质感统一，形成强烈且克制的视觉氛围。",
        "hard_fail": False,
    },
    {
        "id": "detail_finish",
        "display_id": "A5",
        "name": "细节完成度",
        "weight": 0.15,
        "weight_percent": 15,
        "desc": "评估页面在组件、图标、间距、圆角、边框、插图、图表、状态和局部 polish 上是否完成。重点看相似组件规则是否一致，视觉资产是否精修，是否存在明显拼装、错位、粗糙、占位或低成本 demo 痕迹。",
        "score_rule_8": "0-2: 大量粗糙细节、错位、默认控件、占位内容、图片失败或组件风格不统一。\n2-4: 页面完整但细节普通，按钮、卡片、图表、图标和间距仍像快速拼装。\n4-6: 多数组件完成度较好，间距和局部样式稳定，但精修程度和资产质量仍有限。\n6-8: 局部细节高度统一，组件、图标、图表、插图和状态都像完整产品设计系统的一部分。",
        "score_rule_100": "0-25: 大量粗糙细节、错位、默认控件、占位内容、图片失败或组件风格不统一。25-50: 页面完整但细节普通，按钮、卡片、图表、图标和间距仍像快速拼装。50-75: 多数组件完成度较好，间距和局部样式稳定，但精修程度和资产质量仍有限。75-100: 局部细节高度统一，组件、图标、图表、插图和状态都像完整产品设计系统的一部分。",
        "hard_fail": False,
    },
    {
        "id": "basic_usability",
        "display_id": "A6",
        "name": "基础可用性",
        "weight": 0.05,
        "weight_percent": 5,
        "desc": "评估静态截图中的基础可读、可辨认和可操作性。它不是产品功能评分，只用于防止明显不可读、遮挡、错位、核心结构失败的页面被视觉氛围抬高。",
        "score_rule_8": "0-2: 核心信息不可读，按钮/输入/导航被遮挡或错位，布局严重影响理解。\n2-4: 基本能理解，但存在明显拥挤、溢出、低对比、遮挡或响应式问题。\n4-6: 主要内容和操作清楚，只有局部小问题，不明显阻碍静态理解。\n6-8: 信息清晰、控件可辨认、结构稳定，桌面/移动截图中都没有明显基础可用性问题。",
        "score_rule_100": "0-25: 核心信息不可读，按钮/输入/导航被遮挡或错位，布局严重影响理解。25-50: 基本能理解，但存在明显拥挤、溢出、低对比、遮挡或响应式问题。50-75: 主要内容和操作清楚，只有局部小问题，不明显阻碍静态理解。75-100: 信息清晰、控件可辨认、结构稳定，桌面/移动截图中都没有明显基础可用性问题。",
        "hard_fail": False,
    },
]

AXIS_IDS = [str(axis["id"]) for axis in AXES]
AXIS_WEIGHTS = {str(axis["id"]): float(axis["weight"]) for axis in AXES}
AXES_BY_ID = {str(axis["id"]): axis for axis in AXES}

RUBRIC = {
    "score_scale": SCORE_SCALE,
    "bias": "design-site aesthetics",
    "weights": AXIS_WEIGHTS,
}

INTERNAL_RUBRIC = [
    {
        key: value
        for key, value in axis.items()
        if key not in {"score_rule_8", "score_rule_100"}
    }
    | {"score_rule": axis["score_rule_8"]}
    for axis in AXES
]
EXTERNAL_RUBRIC = [
    {
        key: value
        for key, value in axis.items()
        if key not in {"score_rule_8", "score_rule_100"}
    }
    | {"score_rule": axis["score_rule_100"]}
    for axis in AXES
]

VIEW_DISPLAY_NAMES = {"desktop": "web", "mobile": "mobile"}
BOUNDARY_BUCKET_SCORES = {
    "[0,10)": 0.4,
    "[10,20)": 1.2,
    "[20,30)": 2.0,
    "[30,40)": 2.8,
    "[40,50)": 3.6,
    "[50,60)": 4.4,
    "[60,70)": 5.2,
    "[70,80)": 6.0,
    "[80,100]": 7.2,
}


def round_3(value: Any) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))


def clamp_score(value: Any) -> float:
    score = round(float(value), 1)
    return max(SCORE_MIN, min(SCORE_MAX, score))


def score_to_100(score: Any) -> float | None:
    if score is None:
        return None
    return round_3(Decimal(str(score)) * Decimal("12.5"))


def display_viewport(viewport: Any) -> str | None:
    if viewport is None:
        return None
    text = str(viewport)
    return VIEW_DISPLAY_NAMES.get(text, text)


def axis_weighted_scores(axis_scores: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for axis_id in AXIS_IDS:
        meta = AXES_BY_ID[axis_id]
        score = score_to_100(axis_scores.get(axis_id))
        weight = meta["weight"]
        weighted_contribution = (
            round_3(Decimal(str(score)) * Decimal(str(weight)))
            if score is not None
            else None
        )
        rows.append(
            {
                "id": axis_id,
                "display_id": meta["display_id"],
                "name": meta["name"],
                "score": score,
                "weight": weight,
                "weighted_contribution_100": weighted_contribution,
            }
        )
    return rows


def weighted_total_100(rows: list[dict[str, Any]]) -> float | None:
    values = [
        Decimal(str(row["weighted_contribution_100"]))
        for row in rows
        if row.get("weighted_contribution_100") is not None
    ]
    if not values:
        return None
    return round_3(sum(values))
