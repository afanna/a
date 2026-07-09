from __future__ import annotations

from ..math_utils import normalize_text, text_similarity
from ..models import MetricResult
from .base import BaseMetric, MetricContext, register_metric


@register_metric
class CoverageMetric(BaseMetric):
    name = "coverage"
    dimension = "information"

    def evaluate(self, context: MetricContext) -> MetricResult:
        required = context.dsl.required_texts
        if not required:
            return MetricResult(
                name=self.name,
                dimension=self.dimension,
                score=0.0,
                value=0.0,
                ideal=1.0,
                deviation=1.0,
                formula="coverage = matched / required",
                details={"reason": "no DSL required display text found"},
            )
        threshold = float(context.config.section("information").get("text_match_similarity", 0.9))
        ocr_texts = [block.text for block in context.vision.text_blocks]
        matched: list[str] = []
        missing: list[str] = []
        for item in required:
            best = max((text_similarity(item.text, ocr) for ocr in ocr_texts), default=0.0)
            if best >= threshold:
                matched.append(item.text)
            else:
                missing.append(item.text)
        coverage = len(matched) / len(required)
        return MetricResult(
            name=self.name,
            dimension=self.dimension,
            score=round(coverage * 100, 2),
            value=round(coverage, 4),
            ideal=1.0,
            deviation=round(1.0 - coverage, 4),
            formula="score = 100 * coverage",
            confidence=context.vision.confidence,
            details={"matched": matched, "missing": missing, "required_count": len(required)},
        )


@register_metric
class TruncationMetric(BaseMetric):
    name = "truncation"
    dimension = "information"

    def evaluate(self, context: MetricContext) -> MetricResult:
        required = context.dsl.required_texts
        if not required:
            return MetricResult(
                name=self.name,
                dimension=self.dimension,
                score=0.0,
                value=1.0,
                ideal=0.0,
                deviation=1.0,
                formula="score = 100 * (1 - truncation_rate)",
                details={"reason": "no DSL required display text found"},
            )
        section = context.config.section("information")
        partial_threshold = float(section.get("partial_match_similarity", 0.55))
        full_threshold = float(section.get("text_match_similarity", 0.9))
        low_confidence = float(section.get("ocr_low_confidence", 0.6))
        ocr_texts = [block.text for block in context.vision.text_blocks]
        if not ocr_texts:
            return MetricResult(
                name=self.name,
                dimension=self.dimension,
                score=0.0,
                value=1.0,
                ideal=0.0,
                deviation=1.0,
                formula="score = 100 * (1 - truncation_rate)",
                confidence=0.0,
                details={"reason": "no OCR text found"},
            )
        truncated: list[str] = []
        for item in required:
            best = max((text_similarity(item.text, ocr) for ocr in ocr_texts), default=0.0)
            if partial_threshold <= best < full_threshold:
                truncated.append(item.text)
        ellipsis = [block.text for block in context.vision.text_blocks if normalize_text(block.text).endswith(("...", "..", "…"))]
        low_conf = [block.text for block in context.vision.text_blocks if block.confidence < low_confidence]
        truncation_rate = min(1.0, (len(truncated) + len(ellipsis) + len(low_conf)) / max(1, len(required)))
        return MetricResult(
            name=self.name,
            dimension=self.dimension,
            score=round(100 * (1 - truncation_rate), 2),
            value=round(truncation_rate, 4),
            ideal=0.0,
            deviation=round(truncation_rate, 4),
            formula="score = 100 * (1 - truncation_rate)",
            confidence=context.vision.confidence,
            details={"truncated": truncated, "ellipsis": ellipsis, "low_confidence_texts": low_conf},
        )


@register_metric
class DuplicateMetric(BaseMetric):
    name = "duplicate"
    dimension = "information"

    def evaluate(self, context: MetricContext) -> MetricResult:
        texts = [block.text for block in context.vision.text_blocks if normalize_text(block.text)]
        if not context.dsl.required_texts:
            return MetricResult(
                name=self.name,
                dimension=self.dimension,
                score=0.0,
                value=1.0,
                ideal=0.0,
                deviation=1.0,
                formula="score = 100 * (1 - duplicate_rate)",
                details={"reason": "no DSL required display text found"},
            )
        if not texts:
            return MetricResult(
                name=self.name,
                dimension=self.dimension,
                score=0.0,
                value=1.0,
                ideal=0.0,
                deviation=1.0,
                formula="score = 100 * (1 - duplicate_rate)",
                confidence=0.0,
                details={"reason": "no OCR text found"},
            )
        threshold = float(context.config.section("information").get("duplicate_similarity", 0.9))
        duplicates: list[tuple[str, str]] = []
        for left_index, left in enumerate(texts):
            for right in texts[left_index + 1 :]:
                if text_similarity(left, right) >= threshold:
                    duplicates.append((left, right))
        duplicate_rate = len(duplicates) / max(1, len(texts))
        return MetricResult(
            name=self.name,
            dimension=self.dimension,
            score=round(100 * (1 - min(1.0, duplicate_rate)), 2),
            value=round(duplicate_rate, 4),
            ideal=0.0,
            deviation=round(duplicate_rate, 4),
            formula="score = 100 * (1 - duplicate_rate)",
            confidence=context.vision.confidence,
            details={"duplicates": duplicates},
        )
