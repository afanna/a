"""Color Harmony Rules (Dimension: color, 15 pts).

Rule 3.1 - Too Many Colors: excessive dominant colors.
Rule 3.2 - Contrast Ratio: text-background contrast below WCAG threshold.
Rule 3.3 - High Saturation: overly vivid/garish colors.
Rule 3.4 - Color Conflict: complementary hue clashes (e.g. red-green).
"""

from __future__ import annotations

from card_scorer.models import RuleResult, Severity, ScoringContext
from card_scorer.rules.base import Rule
from card_scorer.rules.registry import register_rule


@register_rule
class TooManyColorsRule(Rule):
    """R3.1: Too many dominant colors make the card look chaotic."""

    rule_id = "R3.1"
    rule_name = "颜色过多"
    dimension = "color"
    severity = Severity.MINOR
    max_deduction = 5.0

    def evaluate(self, ctx: ScoringContext) -> RuleResult:
        max_colors = self.cfg.threshold("color", "max_dominant_colors")
        # Only count colors with significant proportion (> 5%)
        significant = [c for c in ctx.dominant_colors if c.proportion > 0.05]
        count = len(significant)

        if count <= max_colors:
            return self._pass({"dominant_color_count": count})

        deduction = self.cfg.threshold("color", "too_many_colors_deduction")
        return self._fail(
            deduction=deduction,
            evidence={"dominant_color_count": count, "max_allowed": max_colors},
            explanation=f"主色数量 {count} 超过建议的 {max_colors} 种",
            suggestion="精简配色方案, 使用 3-5 种主色",
        )


@register_rule
class ContrastRatioRule(Rule):
    """R3.2: Text-background contrast below WCAG AA standard."""

    rule_id = "R3.2"
    rule_name = "对比度不足"
    dimension = "color"
    severity = Severity.MAJOR
    max_deduction = 5.0

    def evaluate(self, ctx: ScoringContext) -> RuleResult:
        min_ratio = self.cfg.threshold("color", "contrast_ratio_min")
        contrast_info = ctx.features.get("min_contrast", {})
        actual_ratio = contrast_info.get("min_ratio", 21.0)

        if actual_ratio >= min_ratio:
            return self._pass({"contrast_ratio": round(actual_ratio, 2)})

        deduction = self.cfg.threshold("color", "contrast_deduction")
        return self._fail(
            deduction=deduction,
            evidence={
                "contrast_ratio": round(actual_ratio, 2),
                "min_required": min_ratio,
                "pair": contrast_info.get("pair", []),
            },
            explanation=f"最低对比度 {actual_ratio:.1f}:1 低于 WCAG AA 标准 {min_ratio}:1",
            suggestion="增大文字与背景之间的色彩对比度",
        )


@register_rule
class HighSaturationRule(Rule):
    """R3.3: Overly saturated colors are visually harsh."""

    rule_id = "R3.3"
    rule_name = "高饱和度"
    dimension = "color"
    severity = Severity.MINOR
    max_deduction = 3.0

    def evaluate(self, ctx: ScoringContext) -> RuleResult:
        high_sat = ctx.features.get("high_saturation", [])

        if not high_sat:
            return self._pass()

        deduction = self.cfg.threshold("color", "high_saturation_deduction")
        return self._fail(
            deduction=deduction,
            evidence={"high_saturation_colors": high_sat},
            explanation=f"检测到 {len(high_sat)} 种过高饱和度的颜色",
            suggestion="降低颜色饱和度, 使配色更柔和",
        )


@register_rule
class ColorConflictRule(Rule):
    """R3.4: Complementary color clashes (e.g. red-green, orange-blue)."""

    rule_id = "R3.4"
    rule_name = "配色冲突"
    dimension = "color"
    severity = Severity.MAJOR
    max_deduction = 5.0

    def evaluate(self, ctx: ScoringContext) -> RuleResult:
        conflicts = ctx.features.get("color_conflicts", [])

        if not conflicts:
            return self._pass()

        deduction = self.cfg.threshold("color", "color_conflict_deduction")
        return self._fail(
            deduction=deduction,
            evidence={"conflicts": conflicts},
            explanation=f"检测到 {len(conflicts)} 组互补色冲突",
            suggestion="避免使用互补色的高饱和度搭配",
        )
