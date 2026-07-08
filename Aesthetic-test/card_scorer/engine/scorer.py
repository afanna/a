"""Scoring Engine with RuleBook integration.

Orchestrates rule evaluation, deduction accumulation, dimension aggregation,
and FAIL judgment. Now uses the rule registry and RuleBook for dynamic rule loading.

Flow:
    100 pts -> load enabled rules from registry -> evaluate rules ->
    accumulate deductions -> check FAIL -> cap score if needed -> build ScoringReport
"""

from __future__ import annotations

import logging
from collections import defaultdict

from card_scorer.configs.loader import Config
from card_scorer.engine.fail_checker import check_fail
from card_scorer.models import (
    DimensionScore,
    RuleResult,
    ScoringContext,
    ScoringReport,
)
from card_scorer.rules.base import Rule
from card_scorer.rules.registry import build_rulebook, get_registered_rules

logger = logging.getLogger(__name__)


def _collect_all_rules(profile: str = "default") -> list[Rule]:
    """Gather all enabled rules from the registry based on profile."""
    # Build rulebook from profile
    rulebook = build_rulebook(profile=profile)
    
    # Get all registered rule classes
    registry = get_registered_rules()
    
    # Instantiate only enabled rules
    rules: list[Rule] = []
    for rule_id in rulebook.list_enabled_rules():
        rule_class = registry.get(rule_id)
        if rule_class:
            rules.append(rule_class())
        else:
            logger.warning(f"Rule {rule_id} is enabled but not found in registry")
    
    logger.info(f"Loaded {len(rules)} rules from profile '{rulebook.profile_name}'")
    return rules


def score(ctx: ScoringContext, profile: str = "default") -> ScoringReport:
    """Run all enabled rules and produce a ScoringReport.

    Pure deduction system:
        total = base_score - sum(deductions)
        if FAIL triggered: total = min(total, fail_cap)
    
    Args:
        ctx: Scoring context with extracted features
        profile: Validation profile name (default, strict, quick)
    """
    cfg = Config.load()
    base = cfg.base_score
    fail_cap = cfg.fail_cap

    rules = _collect_all_rules(profile=profile)
    all_results: list[RuleResult] = []

    for rule in rules:
        try:
            result = rule.evaluate(ctx)
            all_results.append(result)
        except Exception as e:
            logger.error("Rule %s raised: %s", rule.rule_id, e, exc_info=True)
            # Create an error result so scoring continues
            all_results.append(RuleResult(
                rule_id=rule.rule_id,
                rule_name=rule.rule_name,
                dimension=rule.dimension,
                passed=True,
                score_delta=0.0,
                severity=rule.severity,
                evidence={"error": str(e)},
                explanation=f"Rule evaluation error: {e}",
            ))

    # Deductions
    deductions = [r for r in all_results if not r.passed]
    total_deduction = sum(abs(r.score_delta) for r in deductions)
    total = base - total_deduction

    # FAIL check
    fail_triggered = check_fail(all_results)
    if fail_triggered:
        total = min(total, fail_cap)

    total = max(0.0, total)

    # Dimension aggregation
    dim_results: dict[str, list[RuleResult]] = defaultdict(list)
    for r in all_results:
        dim_results[r.dimension].append(r)

    dimensions: list[DimensionScore] = []
    dim_configs = cfg.weights_raw().get("dimensions", {})
    
    # Use actual dimensions found in results
    found_dimensions = set(r.dimension for r in all_results)
    
    for dim_key in found_dimensions:
        dim_cfg = dim_configs.get(dim_key, {})
        results_for_dim = dim_results.get(dim_key, [])
        actual_ded = sum(abs(r.score_delta) for r in results_for_dim if not r.passed)
        dimensions.append(DimensionScore(
            dimension=dim_key,
            dimension_name=dim_cfg.get("name", dim_key),
            max_deduction=float(dim_cfg.get("max_deduction", 0)),
            actual_deduction=actual_ded,
            rule_results=results_for_dim,
        ))

    status = "FAIL" if fail_triggered else "PASS"

    # ✨ P0-2 修复：收集警告信息
    warnings = []
    if ctx.dsl_status == "PARSE_FAILED":
        warnings.append(f"⚠️ DSL 解析失败：{ctx.dsl_path}")
        warnings.append("   结构规范维度（R5.1-R5.4）无法评估")
    elif ctx.dsl_status == "FILE_NOT_FOUND":
        warnings.append(f"⚠️ DSL 文件未找到：{ctx.dsl_path}")

    report = ScoringReport(
        total_score=round(total, 1),
        status=status,
        fail_triggered=fail_triggered,
        dimensions=dimensions,
        all_results=all_results,
        deduction_details=deductions,
        warnings=warnings,  # ✨ 新增
        metadata={
            "image_path": ctx.image_path,
            "query": ctx.query,
            "image_size": f"{ctx.image_width}x{ctx.image_height}",
            "text_count": len(ctx.text_elements),
            "component_count": len(ctx.component_elements),
            "color_count": len(ctx.dominant_colors),
            "profile": profile,
            "dsl_status": ctx.dsl_status,  # ✨ 新增
        },
    )

    logger.info("Score: %.1f (%s) -- %d deductions", total, status, len(deductions))
    return report
