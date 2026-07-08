"""Structure Rules (Dimension: structure, 10 pts).



Phase 3 rules -- DSL-based structural analysis.



Rule 5.1 - Nesting Depth: component nesting too deep.

Rule 5.2 - Empty Container: containers with no children.

Rule 5.3 - Border Radius Consistency: too many radius levels.

Rule 5.4 - Excessive Decoration: too many decorative elements.

"""



from __future__ import annotations



from card_scorer.extractors.dsl_extractor import find_empty_containers, get_max_nesting_depth

from card_scorer.models import RuleResult, Severity, ScoringContext

from card_scorer.rules.base import Rule

from card_scorer.rules.registry import register_rule





@register_rule

class NestingDepthRule(Rule):

    """R5.1: Component nesting should not be too deep."""



    rule_id = "R5.1"

    rule_name = "嵌套深度"

    dimension = "structure"

    severity = Severity.MINOR

    max_deduction = 3.0



    def evaluate(self, ctx: ScoringContext) -> RuleResult:

        if ctx.dsl_tree is None:

            return self._pass({"reason": "no DSL provided", "note": "structure rules require DSL input, skipped"})



        max_allowed = self.cfg.threshold("structure", "max_nesting_depth")

        actual = get_max_nesting_depth(ctx.dsl_tree)



        if actual <= max_allowed:

            return self._pass({"depth": actual})



        deduction = self.cfg.threshold("structure", "nesting_deduction")

        return self._fail(

            deduction=deduction,

            evidence={"depth": actual, "max_allowed": max_allowed},

            explanation=f"DSL 嵌套深度 {actual} 超过阈值 {max_allowed}",

            suggestion="扁平化组件结构, 减少不必要的嵌套",

        )





@register_rule

class EmptyContainerRule(Rule):

    """R5.2: Containers should not be empty."""



    rule_id = "R5.2"

    rule_name = "空容器"

    dimension = "structure"

    severity = Severity.MINOR

    max_deduction = 3.0



    def evaluate(self, ctx: ScoringContext) -> RuleResult:

        if ctx.dsl_tree is None:

            return self._pass({"reason": "no DSL provided", "note": "structure rules require DSL input, skipped"})



        empty = find_empty_containers(ctx.dsl_tree)



        if not empty:

            return self._pass()



        deduction = self.cfg.threshold("structure", "empty_container_deduction")

        return self._fail(

            deduction=deduction,

            evidence={"empty_containers": len(empty)},

            explanation=f"检测到 {len(empty)} 个空容器节点",

            suggestion="移除空容器或添加子元素",

        )





@register_rule

class BorderRadiusConsistencyRule(Rule):

    """R5.3: Border radius should not have too many distinct levels."""



    rule_id = "R5.3"

    rule_name = "圆角一致性"

    dimension = "structure"

    severity = Severity.MINOR

    max_deduction = 2.0



    def evaluate(self, ctx: ScoringContext) -> RuleResult:

        if ctx.dsl_tree is None:

            return self._pass({"reason": "no DSL provided", "note": "structure rules require DSL input, skipped"})



        # Collect all borderRadius values from DSL

        radii: set[float] = set()



        def _visitor(node: dict, depth: int) -> None:

            if isinstance(node, dict):

                for key in ("borderRadius", "border_radius", "radius"):

                    if key in node:

                        try:

                            radii.add(float(node[key]))

                        except (TypeError, ValueError):

                            pass



        from card_scorer.extractors.dsl_extractor import walk_dsl

        walk_dsl(ctx.dsl_tree, _visitor)



        max_levels = self.cfg.threshold("structure", "border_radius_levels_max")

        if len(radii) <= max_levels:

            return self._pass({"radius_levels": len(radii)})



        deduction = self.cfg.threshold("structure", "border_radius_deduction")

        return self._fail(

            deduction=deduction,

            evidence={"radius_levels": len(radii), "radii": sorted(radii), "max_allowed": max_levels},

            explanation=f"圆角层级 {len(radii)} 种, 超过建议的 {max_levels} 种",

            suggestion="统一圆角值, 减少圆角变体",

        )





@register_rule

class ExcessiveDecorationRule(Rule):

    """R5.4: Too many decorative elements clutter the card."""



    rule_id = "R5.4"

    rule_name = "装饰过多"

    dimension = "structure"

    severity = Severity.MINOR

    max_deduction = 2.0



    def evaluate(self, ctx: ScoringContext) -> RuleResult:

        if ctx.dsl_tree is None:

            return self._pass({"reason": "no DSL provided", "note": "structure rules require DSL input, skipped"})



        # Count nodes tagged as decorative

        deco_count = 0



        def _visitor(node: dict, depth: int) -> None:

            nonlocal deco_count

            if isinstance(node, dict):

                node_type = str(node.get("type", "")).lower()

                if any(kw in node_type for kw in ("decoration", "divider", "separator", "ornament")):

                    deco_count += 1



        from card_scorer.extractors.dsl_extractor import walk_dsl

        walk_dsl(ctx.dsl_tree, _visitor)



        max_deco = self.cfg.threshold("structure", "decoration_count_max")

        if deco_count <= max_deco:

            return self._pass({"decoration_count": deco_count})



        deduction = self.cfg.threshold("structure", "decoration_deduction")

        return self._fail(

            deduction=deduction,

            evidence={"decoration_count": deco_count, "max_allowed": max_deco},

            explanation=f"装饰元素 {deco_count} 个, 超过建议的 {max_deco} 个",

            suggestion="减少装饰元素, 保持视觉清洁",

        )





