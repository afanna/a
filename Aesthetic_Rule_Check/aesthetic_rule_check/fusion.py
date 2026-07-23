from __future__ import annotations

from collections import defaultdict

from .config import Config
from .deductions import collect_deductions, hard_caps_for, prompt_suggestions_for
from .localization import metric_label, reason_label
from .math_utils import clamp, weighted_average
from .metrics import MetricContext, create_metrics
from .models import DimensionResult, EvaluationResult, MetricResult


FALLBACK_DIMENSION_ORDER = ["geometry", "information", "layout", "visual", "consistency"]


def run_metrics(context: MetricContext) -> list[MetricResult]:
    results: list[MetricResult] = []
    for metric in create_metrics():
        try:
            results.append(metric.evaluate(context))
        except Exception as exc:
            results.append(
                MetricResult(
                    name=metric.name,
                    dimension=metric.dimension,
                    score=None,
                    confidence=0.0,
                    status="error",
                    details={"error": str(exc)},
                )
            )
    return results


def build_dimensions(metrics: list[MetricResult], config: Config) -> list[DimensionResult]:
    grouped: dict[str, list[MetricResult]] = defaultdict(list)
    for metric in metrics:
        grouped[metric.dimension].append(metric)

    dimensions: list[DimensionResult] = []
    dimension_order = config.dimension_names() or FALLBACK_DIMENSION_ORDER
    dimension_order.extend(dimension for dimension in grouped if dimension not in dimension_order)
    for dimension in dimension_order:
        metric_results = grouped.get(dimension, [])
        weighted_scores: list[tuple[float, float]] = []
        for metric in metric_results:
            if metric.score is None:
                continue
            weight = float(config.metric_config(dimension, metric.name).get("weight", 0))
            weighted_scores.append((metric.score, weight))
        score = weighted_average(weighted_scores) if weighted_scores else 0.0
        dimensions.append(
            DimensionResult(
                name=dimension,
                label=config.dimension_label(dimension),
                score=round(score, 2),
                weight=config.dimension_weight(dimension),
                metrics=metric_results,
            )
        )
    return dimensions


def overall_score(dimensions: list[DimensionResult]) -> float:
    return round(weighted_average((dimension.score, dimension.weight) for dimension in dimensions), 2)


def overall_confidence(metrics: list[MetricResult]) -> float:
    if not metrics:
        return 0.0
    values = [metric.confidence for metric in metrics if metric.status == "ok"]
    errors = sum(1 for metric in metrics if metric.status == "error")
    confidence = sum(values) / len(values) if values else 0.0
    return round(clamp(confidence - errors * 0.08, 0.0, 1.0), 4)


def missing_texts(metrics: list[MetricResult]) -> list[str]:
    for metric in metrics:
        if metric.dimension == "information" and metric.name == "coverage":
            missing = metric.details.get("missing", [])
            return [str(item) for item in missing]
    return []


def warnings_for(context: MetricContext, metrics: list[MetricResult], config: Config) -> list[str]:
    warnings: list[str] = list(context.dsl.warnings)
    for metric in metrics:
        label = metric_label(metric.dimension, metric.name)
        if metric.status == "error":
            warnings.append(f"指标异常：{label}：{metric.details.get('error')}")
        if metric.status == "skipped":
            warnings.append(f"指标跳过：{label}：{reason_label(metric.details.get('reason'))}")
        if metric.score is not None and float(config.metric_config(metric.dimension, metric.name).get("weight", 0)) <= 0:
            warnings.append(f"指标权重未配置为正数：{label}")
    for metric in metrics:
        if metric.dimension != "information" or metric.name != "coverage" or metric.score != 0:
            continue
        reason = metric.details.get("reason")
        if reason:
            warnings.append("信息覆盖率为 0：DSL 中没有提取到必要展示文字。")
        else:
            warnings.append("信息覆盖率为 0：必要 DSL 文字没有匹配到截图 OCR 结果。")
    return warnings


def build_result(context: MetricContext, metrics: list[MetricResult], config: Config) -> EvaluationResult:
    dimensions = build_dimensions(metrics, config)
    raw_overall = overall_score(dimensions)
    deductions = collect_deductions(metrics)
    hard_caps = hard_caps_for(deductions)
    # 封顶融合规则（P0）：
    # 1) 每个触发封顶的扣分项按各自 magnitude 得到递进封顶值（见 deductions.cap_for）。
    # 2) 叠加（stacking）：样本上除第一个触发封顶的扣分 code 外，每个不同的扣分 code
    #    再让最终封顶 -2，最多 -6。按不同 code 计数而非按条数：同一 code 的多条扣分
    #    （例如多条文本缺失）已经由 magnitude（缺失率）体现，不重复惩罚。
    # 3) overall = min(raw_overall, final_min_cap)。
    cap = min((float(item["cap"]) for item in hard_caps), default=100.0)
    cap_codes = {str(item["code"]) for item in hard_caps}
    stacking = min(2 * (len(cap_codes) - 1), 6) if cap_codes else 0
    final_min_cap = cap - stacking
    overall = round(clamp(min(raw_overall, final_min_cap)), 2)
    return EvaluationResult(
        image_path=context.vision.image_path,
        dsl_path=context.dsl.path,
        query=context.query,
        overall=overall,
        raw_overall=raw_overall,
        grade=config.grade_for(overall),
        confidence=overall_confidence(metrics),
        dimensions=dimensions,
        metrics=metrics,
        required_texts=context.dsl.required_texts,
        missing_texts=missing_texts(metrics),
        deductions=deductions,
        prompt_suggestions=prompt_suggestions_for(deductions),
        hard_caps=hard_caps,
        warnings=warnings_for(context, metrics, config),
    )
