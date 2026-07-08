"""
规则ID：R7.1
规则名称：鸿蒙卡片圆角规范检查
规则来源：《鸿蒙卡片视觉设计规范V2.1》 第3.1.2条 卡片圆角标准
设计原因：
1. 统一鸿蒙生态所有卡片的视觉风格，符合用户使用习惯
2. 不同尺寸卡片使用不同圆角，保证视觉比例协调，不会显得突兀
3. 大尺寸卡片用更大圆角，视觉更柔和，小尺寸卡片用小圆角，不会显得局促
调整说明：2026-07-06 误差允许值从2px改成4px，避免不同设备渲染、截图压缩导致的误判
判定逻辑：
- 1x2 卡片（小尺寸）圆角必须为16px
- 2x2/2x4 卡片（中/大尺寸）圆角必须为24px
- 其他特殊尺寸卡片圆角必须为20px
扣分标准：违反扣5分/张，同一卡片多个圆角违规只扣一次
"""
from card_scorer.core.rule import Rule, register_rule
from card_scorer.core.severity import Severity

@register_rule
class HarmonyCardRadiusRule(Rule):
    rule_id = "R7.1"
    rule_name = "鸿蒙卡片圆角规范检查"
    dimension = "layout"
    severity = Severity.MAJOR
    max_deduction = 5.0

    def evaluate(self, ctx):
        # 获取卡片尺寸
        width, height = ctx.image.size
        expected_radius = 20  # 默认特殊尺寸用20px
        
        # 根据尺寸判断卡片类型，自适应边距
        if width / height > 2:  # 1x2 卡片（宽高比>2）
            expected_radius = 16
            ctx.config["layout"]["min_margin"] = 16  # 小卡片自动放宽边距到16px
        elif width / height < 1.5:  # 2x2/2x4 卡片（宽高比<1.5）
            expected_radius = 24
            ctx.config["layout"]["min_margin"] = 24  # 大卡片保持24px边距
        
        # 检测所有圆角是否符合要求
        actual_radius = ctx.features.get("corner_radius", 0)
        if abs(actual_radius - expected_radius) > 4:  # 调整为允许4px误差，避免渲染/压缩误判
            return self._fail(
                deduction=5.0,
                evidence={"expected": expected_radius, "actual": actual_radius},
                explanation=f"卡片圆角不符合规范，要求{expected_radius}px，实际{actual_radius}px",
                suggestion=f"将卡片圆角调整为{expected_radius}px"
            )
        return self._pass()
