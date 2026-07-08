"""Visual Hierarchy Rules (Dimension: hierarchy, 10 pts).



Rule 4.1 - Visual Center Offset: center of mass deviates too far.

Rule 4.2 - Density Balance: quadrant density ratio too extreme.

Rule 4.3 - Size Hierarchy: heading-body ratio out of range.

"""



from __future__ import annotations



from card_scorer.models import RuleResult, Severity, ScoringContext

from card_scorer.rules.base import Rule

from card_scorer.rules.registry import register_rule





@register_rule

class VisualCenterOffsetRule(Rule):

    """R4.1: Visual center should be near the geometric center."""



    rule_id = "R4.1"

    rule_name = "视觉重心偏移"

    dimension = "hierarchy"

    severity = Severity.MINOR

    max_deduction = 4.0



    def evaluate(self, ctx: ScoringContext) -> RuleResult:

        offset = ctx.features.get("visual_center_offset", {})

        norm = offset.get("offset_norm", 0.0)

        max_offset = self.cfg.threshold("hierarchy", "visual_center_offset_max")



        if norm <= max_offset:

            return self._pass({"offset_norm": round(norm, 3)})



        deduction = self.cfg.threshold("hierarchy", "visual_center_deduction")

        return self._fail(

            deduction=deduction,

            evidence={

                "offset_x": round(offset.get("offset_x", 0), 3),

                "offset_y": round(offset.get("offset_y", 0), 3),

                "offset_norm": round(norm, 3),

                "max_allowed": max_offset,

            },

            explanation=f"视觉重心偏移 {norm:.2f} 超过阈值 {max_offset}",

            suggestion="调整内容分布使视觉重心更居中",

        )





@register_rule

class DensityBalanceRule(Rule):

    """R4.2: Element distribution should be balanced across quadrants."""



    rule_id = "R4.2"

    rule_name = "密度均衡"

    dimension = "hierarchy"

    severity = Severity.MINOR

    max_deduction = 3.0



    def evaluate(self, ctx: ScoringContext) -> RuleResult:

        balance = ctx.features.get("density_balance", {})

        ratio = balance.get("ratio", 1.0)

        max_ratio = self.cfg.threshold("hierarchy", "quadrant_density_ratio_max")



        if ratio <= max_ratio:

            return self._pass({"ratio": round(ratio, 2)})



        deduction = self.cfg.threshold("hierarchy", "density_balance_deduction")

        return self._fail(

            deduction=deduction,

            evidence={

                "ratio": round(ratio, 2),

                "max_quadrant": balance.get("max_quadrant"),

                "min_quadrant": balance.get("min_quadrant"),

                "max_allowed": max_ratio,

            },

            explanation=f"象限密度比 {ratio:.1f}:1 超过阈值 {max_ratio}:1",

            suggestion="重新分布内容使各区域更均衡",

        )





@register_rule

class SizeHierarchyRule(Rule):

    """R4.3: Heading should be noticeably larger than body text."""



    rule_id = "R4.3"

    rule_name = "尺寸层级"

    dimension = "hierarchy"

    severity = Severity.MINOR

    max_deduction = 3.0



    def evaluate(self, ctx: ScoringContext) -> RuleResult:

        sh = ctx.features.get("size_hierarchy", {})

        ratio = sh.get("ratio", 1.0)

        min_ratio = self.cfg.threshold("hierarchy", "heading_body_ratio_min")

        max_ratio = self.cfg.threshold("hierarchy", "heading_body_ratio_max")



        if len(ctx.text_elements) < 2:

            return self._pass({"reason": "too few text elements"})



        if min_ratio <= ratio <= max_ratio:

            return self._pass({"ratio": round(ratio, 2)})



        deduction = self.cfg.threshold("hierarchy", "size_hierarchy_deduction")

        if ratio < min_ratio:

            explanation = f"标题/正文字号比 {ratio:.2f} 过小 (建议 >= {min_ratio})"

            suggestion = "增大标题字号或减小正文字号"

        else:

            explanation = f"标题/正文字号比 {ratio:.2f} 过大 (建议 <= {max_ratio})"

            suggestion = "缩小标题字号差距"



        return self._fail(

            deduction=deduction,

            evidence={"ratio": round(ratio, 2), "min": min_ratio, "max": max_ratio},

            explanation=explanation,

            suggestion=suggestion,

        )





