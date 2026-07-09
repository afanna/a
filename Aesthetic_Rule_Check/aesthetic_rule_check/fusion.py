from __future__ import annotations

from collections import defaultdict

from .config import Config
from .math_utils import clamp, weighted_average
from .metrics import MetricContext, create_metrics
from .models import DimensionResult, EvaluationResult, MetricResult


FALLBACK_DIMENSION_ORDER = ["information", "layout", "visual", "consistency"]


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
        if metric.status == "error":
            warnings.append(f"Metric error: {metric.dimension}.{metric.name}: {metric.details.get('error')}")
        if metric.status == "skipped":
            warnings.append(f"Metric skipped: {metric.dimension}.{metric.name}: {metric.details.get('reason')}")
        if metric.score is not None and float(config.metric_config(metric.dimension, metric.name).get("weight", 0)) <= 0:
            warnings.append(f"Metric has no positive configured weight: {metric.dimension}.{metric.name}")
    for metric in metrics:
        if metric.dimension != "information" or metric.name != "coverage" or metric.score != 0:
            continue
        reason = metric.details.get("reason")
        if reason:
            warnings.append("Information coverage is 0 because no DSL required display text was found.")
        else:
            warnings.append("Information coverage is 0 because no required DSL text matched OCR output.")
    return warnings


def build_result(context: MetricContext, metrics: list[MetricResult], config: Config) -> EvaluationResult:
    dimensions = build_dimensions(metrics, config)
    overall = overall_score(dimensions)
    return EvaluationResult(
        image_path=context.vision.image_path,
        dsl_path=context.dsl.path,
        query=context.query,
        overall=overall,
        grade=config.grade_for(overall),
        confidence=overall_confidence(metrics),
        dimensions=dimensions,
        metrics=metrics,
        required_texts=context.dsl.required_texts,
        missing_texts=missing_texts(metrics),
        warnings=warnings_for(context, metrics, config),
    )
