"""Visual Consistency Rules (Dimension: consistency, 20 pts).



VC-1: Alignment consistency

VC-2: Spacing consistency

VC-3: Font rhythm

VC-4: Component rhythm

VC-5: Icon proportion

VC-6: Text-image ratio

VC-7: Margin consistency

VC-8: Grid alignment



These are the CORE rules -- humans are most sensitive to these.

"""



from __future__ import annotations



from card_scorer.models import RuleResult, Severity, ScoringContext

from card_scorer.rules.base import Rule

from card_scorer.rules.registry import register_rule





@register_rule

class AlignmentConsistencyRule(Rule):

    """VC-1: Elements should align to a small number of axes."""



    rule_id = "VC-1"

    rule_name = "对齐一致性"

    dimension = "consistency"

    severity = Severity.MAJOR

    max_deduction = 6.0



    def evaluate(self, ctx: ScoringContext) -> RuleResult:

        alignment = ctx.features.get("alignment", {})

        outlier_ratio = alignment.get("outlier_ratio", 0.0)

        num_left = alignment.get("num_left_clusters", 1)

        num_elements = len(ctx.text_elements) + len(ctx.component_elements)



        # ✨ P0-1 修复：小样本保护

        if num_elements < 3:

            return self._pass({

                "reason": "样本不足",

                "element_count": num_elements,

                "note": "至少需要 3 个元素才能可靠分析对齐一致性"

            })



        # Too many alignment axes or high outlier ratio

        if outlier_ratio > 0.4 or num_left > 5:

            deduction = self.cfg.threshold("consistency", "alignment_deduction")

            return self._fail(

                deduction=deduction,

                evidence={

                    "num_left_clusters": num_left,

                    "outlier_ratio": round(outlier_ratio, 3),

                    "element_count": num_elements,

                },

                explanation=f"检测到 {num_left} 条对齐轴线, 离群率 {outlier_ratio:.0%}",

                suggestion="减少对齐轴线数量, 使元素对齐到统一的网格",

            )



        return self._pass({

            "num_left_clusters": num_left,

            "outlier_ratio": round(outlier_ratio, 3),

            "element_count": num_elements

        })





@register_rule

class SpacingConsistencyRule(Rule):

    """VC-2: Vertical gaps between elements should be consistent."""



    rule_id = "VC-2"

    rule_name = "间距一致性"

    dimension = "consistency"

    severity = Severity.MAJOR

    max_deduction = 5.0



    def evaluate(self, ctx: ScoringContext) -> RuleResult:

        spacing = ctx.features.get("spacing", {})

        cv = spacing.get("cv", 0.0)

        sample_size = spacing.get("sample_size", 0)

        threshold = self.cfg.threshold("consistency", "spacing_variance_threshold")



        # ✨ P0-1 修复：小样本保护（统计学要求至少 3 个样本）

        if sample_size < 3:

            return self._pass({

                "reason": "样本不足",

                "sample_size": sample_size,

                "note": "至少需要 3 个间距才能可靠计算变异系数"

            })



        if cv <= threshold:

            return self._pass({"cv": round(cv, 3), "sample_size": sample_size})



        deduction = self.cfg.threshold("consistency", "spacing_deduction")

        return self._fail(

            deduction=deduction,

            evidence={

                "cv": round(cv, 3),

                "mean_gap": round(spacing.get("mean_gap", 0), 1),

                "std_gap": round(spacing.get("std_gap", 0), 1),

                "threshold": threshold,

                "sample_size": sample_size,

            },

            explanation=f"元素间距变异系数 {cv:.2f} 超过阈值 {threshold}",

            suggestion="统一元素间的垂直间距, 保持节奏一致",

        )





@register_rule

class FontRhythmRule(Rule):

    """VC-3: Font size levels should not be too many."""



    rule_id = "VC-3"

    rule_name = "字号节奏"

    dimension = "consistency"

    severity = Severity.MINOR

    max_deduction = 4.0



    def evaluate(self, ctx: ScoringContext) -> RuleResult:

        font_rhythm = ctx.features.get("font_rhythm", {})

        levels = font_rhythm.get("size_levels", 0)

        max_levels = self.cfg.threshold("consistency", "font_size_levels_max")



        if levels <= max_levels:

            return self._pass({"size_levels": levels})



        deduction = self.cfg.threshold("consistency", "font_rhythm_deduction")

        return self._fail(

            deduction=deduction,

            evidence={"size_levels": levels, "max_allowed": max_levels},

            explanation=f"字号层级 {levels} 种, 超过建议的 {max_levels} 种",

            suggestion="精简字号层级, 保持视觉韵律",

        )





@register_rule

class ComponentRhythmRule(Rule):

    """VC-4: Spacing between non-text components should be regular."""



    rule_id = "VC-4"

    rule_name = "组件节奏"

    dimension = "consistency"

    severity = Severity.MINOR

    max_deduction = 4.0



    def evaluate(self, ctx: ScoringContext) -> RuleResult:

        rhythm = ctx.features.get("component_rhythm", {})

        cv = rhythm.get("cv", 0.0)

        sample_size = rhythm.get("sample_size", 0)

        threshold = self.cfg.threshold("consistency", "spacing_variance_threshold")



        # ✨ P0-1 修复：小样本保护

        if sample_size < 3:

            return self._pass({

                "reason": "样本不足",

                "sample_size": sample_size,

                "component_count": len(ctx.component_elements)

            })



        if cv <= threshold:

            return self._pass({"cv": round(cv, 3), "sample_size": sample_size})



        deduction = self.cfg.threshold("consistency", "component_rhythm_deduction")

        return self._fail(

            deduction=deduction,

            evidence={"cv": round(cv, 3), "threshold": threshold, "sample_size": sample_size},

            explanation=f"组件间距变异系数 {cv:.2f} 超过阈值 {threshold}",

            suggestion="统一组件间的间距",

        )





@register_rule

class IconProportionRule(Rule):

    """VC-5: Icon area should be proportional to card area."""



    rule_id = "VC-5"

    rule_name = "图标比例"

    dimension = "consistency"

    severity = Severity.MINOR

    max_deduction = 3.0



    def evaluate(self, ctx: ScoringContext) -> RuleResult:

        icon = ctx.features.get("icon_proportion", {})

        ratio = icon.get("ratio", 0.0)

        ratio_min = self.cfg.threshold("consistency", "icon_ratio_min")

        ratio_max = self.cfg.threshold("consistency", "icon_ratio_max")



        # Only check if there are components

        if not ctx.component_elements:

            return self._pass({"reason": "no icons detected"})



        if ratio_min <= ratio <= ratio_max:

            return self._pass({"ratio": round(ratio, 4)})



        deduction = self.cfg.threshold("consistency", "icon_proportion_deduction")

        if ratio < ratio_min:

            explanation = f"图标面积占比 {ratio:.2%} 过小 (阈值 {ratio_min:.0%})"

            suggestion = "增大图标尺寸"

        else:

            explanation = f"图标面积占比 {ratio:.2%} 过大 (阈值 {ratio_max:.0%})"

            suggestion = "缩小图标尺寸"



        return self._fail(

            deduction=deduction,

            evidence={"ratio": round(ratio, 4), "min": ratio_min, "max": ratio_max},

            explanation=explanation,

            suggestion=suggestion,

        )





@register_rule

class TextImageRatioRule(Rule):

    """VC-6: Balance between text area and non-text area."""



    rule_id = "VC-6"

    rule_name = "图文比例"

    dimension = "consistency"

    severity = Severity.MINOR

    max_deduction = 3.0



    def evaluate(self, ctx: ScoringContext) -> RuleResult:

        ratio = ctx.features.get("text_image_ratio", 0.5)

        ratio_min = self.cfg.threshold("consistency", "text_image_ratio_min")

        ratio_max = self.cfg.threshold("consistency", "text_image_ratio_max")



        # Skip if no components detected (text-only card is okay)

        if not ctx.component_elements:

            return self._pass({"reason": "text-only card"})



        if ratio_min <= ratio <= ratio_max:

            return self._pass({"ratio": round(ratio, 3)})



        deduction = self.cfg.threshold("consistency", "text_image_ratio_deduction")

        return self._fail(

            deduction=deduction,

            evidence={"ratio": round(ratio, 3), "min": ratio_min, "max": ratio_max},

            explanation=f"图文比例 {ratio:.2f} 瓒呭嚭 [{ratio_min}, {ratio_max}] 鑼冨洿",

            suggestion="调整文本和图标/图片的面积比例",

        )





@register_rule

class MarginConsistencyRule(Rule):

    """VC-7: Left/right margins should be consistent across elements."""



    rule_id = "VC-7"

    rule_name = "边距一致性"

    dimension = "consistency"

    severity = Severity.MINOR

    max_deduction = 3.0



    def evaluate(self, ctx: ScoringContext) -> RuleResult:

        mc = ctx.features.get("margin_consistency", {})

        threshold = self.cfg.threshold("consistency", "margin_consistency_threshold")

        left_cv = mc.get("left_cv", 0.0)

        right_cv = mc.get("right_cv", 0.0)

        sample_size = mc.get("sample_size", 0)



        # ✨ P0-1 修复：小样本保护

        if sample_size < 3:

            return self._pass({

                "reason": "样本不足",

                "sample_size": sample_size,

                "note": "至少需要 3 个元素才能可靠计算边距一致性"

            })



        if left_cv <= threshold and right_cv <= threshold:

            return self._pass({"left_cv": round(left_cv, 3), "right_cv": round(right_cv, 3), "sample_size": sample_size})



        deduction = self.cfg.threshold("consistency", "margin_consistency_deduction")

        return self._fail(

            deduction=deduction,

            evidence={

                "left_cv": round(left_cv, 3),

                "right_cv": round(right_cv, 3),

                "threshold": threshold,

                "sample_size": sample_size,

            },

            explanation=f"左边距变异 {left_cv:.2f}, 右边距变异 {right_cv:.2f} (阈值 {threshold})",

            suggestion="统一各元素的左右边距",

        )





@register_rule

class GridAlignmentRule(Rule):

    """VC-8: Elements should snap to implicit grid lines."""



    rule_id = "VC-8"

    rule_name = "网格对齐"

    dimension = "consistency"

    severity = Severity.MINOR

    max_deduction = 3.0



    def evaluate(self, ctx: ScoringContext) -> RuleResult:

        grid = ctx.features.get("grid_alignment", {})

        x_snap = grid.get("x_snap_ratio", 1.0)

        y_snap = grid.get("y_snap_ratio", 1.0)



        # Consider poor alignment if less than 50% of elements snap

        if x_snap >= 0.5 and y_snap >= 0.5:

            return self._pass({"x_snap": round(x_snap, 3), "y_snap": round(y_snap, 3)})



        deduction = self.cfg.threshold("consistency", "grid_alignment_deduction")

        return self._fail(

            deduction=deduction,

            evidence={"x_snap": round(x_snap, 3), "y_snap": round(y_snap, 3)},

            explanation=f"网格对齐鐜? X={x_snap:.0%}, Y={y_snap:.0%}",

            suggestion="将元素对齐到统一的网格",

        )





