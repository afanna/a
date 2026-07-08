"""Layout & Whitespace Rules (Dimension: layout, 20 pts).



Rule 2.1 - Edge Proximity: elements too close to card boundary.

Rule 2.2 - Element Overlap: overlapping bounding boxes.

Rule 2.3 - Whitespace Ratio: too much or too little whitespace.

Rule 2.4 - Element Overflow: elements extending beyond card boundaries.

"""



from __future__ import annotations



from card_scorer.models import RuleResult, Severity, ScoringContext

from card_scorer.rules.base import Rule

from card_scorer.rules.registry import register_rule





@register_rule

class EdgeProximityRule(Rule):

    """R2.1: Elements too close to the card edge."""



    rule_id = "R2.1"

    rule_name = "贴边检测"

    dimension = "layout"

    severity = Severity.MAJOR

    max_deduction = 5.0



    def evaluate(self, ctx: ScoringContext) -> RuleResult:

        min_margin = self.cfg.threshold("layout", "edge_margin_min_px")

        edge_distances = ctx.features.get("edge_distances", [])



        violations = []

        for ed in edge_distances:

            if ed["min_distance"] < min_margin:

                violations.append({

                    "element_index": ed["element_index"],

                    "min_distance": ed["min_distance"],

                    "threshold": min_margin,

                })



        if not violations:

            return self._pass()



        deduction = self.cfg.threshold("layout", "edge_deduction")

        return self._fail(

            deduction=deduction,

            evidence={"violations": violations, "count": len(violations)},

            explanation=f"{len(violations)} 个元素距卡片边缘不足 {min_margin}px",

            suggestion=f"增加元素到边缘的间距至少 {min_margin}px",

        )





@register_rule

class ElementOverlapRule(Rule):

    """R2.2: Overlapping elements."""



    rule_id = "R2.2"

    rule_name = "元素重叠"

    dimension = "layout"

    severity = Severity.FATAL

    max_deduction = 8.0



    def evaluate(self, ctx: ScoringContext) -> RuleResult:

        overlaps = ctx.features.get("overlaps", [])



        if not overlaps:

            return self._pass()



        deduction = self.cfg.threshold("layout", "overlap_deduction")

        return self._fail(

            deduction=deduction,

            evidence={"overlaps": overlaps, "count": len(overlaps)},

            explanation=f"检测到 {len(overlaps)} 组元素重叠",

            suggestion="调整元素位置或大小消除重叠",

        )





@register_rule

class WhitespaceRatioRule(Rule):

    """R2.3: Whitespace too much or too little."""



    rule_id = "R2.3"

    rule_name = "留白比例"

    dimension = "layout"

    severity = Severity.MINOR

    max_deduction = 5.0



    def evaluate(self, ctx: ScoringContext) -> RuleResult:

        ratio = ctx.features.get("whitespace_ratio", 0.5)

        ws_min = self.cfg.threshold("layout", "whitespace_ratio_min")

        ws_max = self.cfg.threshold("layout", "whitespace_ratio_max")



        if ws_min <= ratio <= ws_max:

            return self._pass({"whitespace_ratio": round(ratio, 3)})



        deduction = self.cfg.threshold("layout", "whitespace_deduction")

        if ratio < ws_min:

            explanation = f"留白比例 {ratio:.1%} 过低 (阈值 {ws_min:.0%}), 内容过于拥挤"

            suggestion = "减少元素数量或增大卡片尺寸"

        else:

            explanation = f"留白比例 {ratio:.1%} 过高 (阈值 {ws_max:.0%}), 内容过于稀疏"

            suggestion = "增加内容或缩小卡片尺寸"



        return self._fail(

            deduction=deduction,

            evidence={"whitespace_ratio": round(ratio, 3), "min": ws_min, "max": ws_max},

            explanation=explanation,

            suggestion=suggestion,

        )





@register_rule

class ElementOverflowRule(Rule):

    """R2.4: Elements extending beyond card boundaries."""



    rule_id = "R2.4"

    rule_name = "元素溢出"

    dimension = "layout"

    severity = Severity.FATAL

    max_deduction = 8.0



    def evaluate(self, ctx: ScoringContext) -> RuleResult:

        overflows = ctx.features.get("overflows", [])



        if not overflows:

            return self._pass()



        deduction = self.cfg.threshold("layout", "element_overflow_deduction")

        return self._fail(

            deduction=deduction,

            evidence={"overflows": overflows, "count": len(overflows)},

            explanation=f"检测到 {len(overflows)} 个元素溢出卡片边界",

            suggestion="调整溢出元素的尺寸或位置",

        )





