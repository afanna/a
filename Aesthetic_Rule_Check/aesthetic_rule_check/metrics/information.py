from __future__ import annotations

import re

from ..math_utils import clamp, normalize_text, text_similarity
from ..models import MetricResult
from .base import BaseMetric, MetricContext, register_metric


NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")
UNIT_ALIASES = {
    "℃": {"℃", "°c", "c", "摄氏度", "度"},
    "°c": {"℃", "°c", "c", "摄氏度", "度"},
    "%": {"%", "％", "percent", "百分比"},
    "％": {"%", "％", "percent", "百分比"},
    "元": {"元", "¥", "￥", "rmb"},
    "¥": {"元", "¥", "￥", "rmb"},
    "￥": {"元", "¥", "￥", "rmb"},
    "分": {"分", "分钟", "min", "mins"},
    "分钟": {"分", "分钟", "min", "mins"},
    "h": {"h", "hr", "hour", "小时"},
    "小时": {"h", "hr", "hour", "小时"},
}
UNIT_RE = re.compile(r"(℃|°c|％|%|元|¥|￥|分钟|小时|分|h|hr|hour|min|mins|摄氏度|度)", re.I)


def text_slots(text: str) -> dict[str, list[str]]:
    raw = str(text or "")
    numbers = [normalize_number(item) for item in NUMBER_RE.findall(raw)]
    units = [normalize_unit(item) for item in UNIT_RE.findall(raw)]
    return {"numbers": [item for item in numbers if item], "units": [item for item in units if item]}


def normalize_number(value: str) -> str:
    try:
        parsed = float(value)
    except ValueError:
        return value
    if parsed.is_integer():
        return str(int(parsed))
    return f"{parsed:.6f}".rstrip("0").rstrip(".")


def normalize_unit(value: str) -> str:
    raw = str(value or "").strip().lower().replace("％", "%")
    if raw == "°c":
        return "℃"
    if raw in {"摄氏度", "度"}:
        return "℃"
    if raw in {"¥", "￥", "rmb"}:
        return "元"
    if raw in {"percent", "百分比"}:
        return "%"
    if raw in {"分钟", "min", "mins"}:
        return "分"
    if raw in {"hr", "hour", "小时"}:
        return "h"
    return raw


def unit_variants(unit: str) -> set[str]:
    normalized = normalize_unit(unit)
    aliases = set()
    for value in UNIT_ALIASES.get(normalized, {normalized}):
        aliases.add(normalize_text(value))
    aliases.add(normalize_text(normalized))
    return aliases


def slots_match(required_text: str, ocr_texts: list[str], full_threshold: float) -> dict:
    best_text = ""
    best_similarity = 0.0
    required_norm = normalize_text(required_text)
    ocr_joined = normalize_text(" ".join(ocr_texts))
    if required_norm and len(required_norm) >= 2 and required_norm in ocr_joined:
        return {"status": "pass", "best_text": required_text, "similarity": 1.0, "score": 1.0}
    for ocr in ocr_texts:
        similarity = text_similarity(required_text, ocr)
        if similarity > best_similarity:
            best_similarity = similarity
            best_text = ocr
    if best_similarity >= full_threshold:
        return {"status": "pass", "best_text": best_text, "similarity": round(best_similarity, 4), "score": 1.0}

    required_slots = text_slots(required_text)
    number_pass = True
    for number in required_slots["numbers"]:
        if normalize_text(number) not in ocr_joined:
            number_pass = False
            break
    unit_pass = True
    missing_units: list[str] = []
    for unit in required_slots["units"]:
        variants = unit_variants(unit)
        if not any(variant and variant in ocr_joined for variant in variants):
            unit_pass = False
            missing_units.append(unit)

    if required_slots["numbers"] and number_pass and required_slots["units"] and not unit_pass:
        return {
            "status": "weak_pass",
            "best_text": best_text,
            "similarity": round(best_similarity, 4),
            "score": 0.75,
            "numbers": required_slots["numbers"],
            "missing_units": missing_units,
        }
    if required_slots["numbers"] and number_pass:
        return {
            "status": "numeric_pass",
            "best_text": best_text,
            "similarity": round(best_similarity, 4),
            "score": 0.85,
            "numbers": required_slots["numbers"],
        }
    missing_numbers = [number for number in required_slots["numbers"] if normalize_text(number) not in ocr_joined]
    return {
        "status": "missing",
        "best_text": best_text,
        "similarity": round(best_similarity, 4),
        "score": 0.0,
        "numbers": required_slots["numbers"],
        "missing_numbers": missing_numbers,
        "units": required_slots["units"],
    }


def deduction(
    code: str,
    severity: str,
    delta: float,
    evidence: str,
    component_id: str | None = None,
    magnitude: float | None = None,
) -> dict:
    record = {
        "code": code,
        "source": "ocr",
        "severity": severity,
        "score_delta": -abs(float(delta)),
        "component_ids": [component_id] if component_id else [],
        "evidence": evidence,
    }
    if magnitude is not None:
        record["magnitude"] = round(clamp(float(magnitude), 0.0, 1.0), 4)
    return record


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
        weak_matched: list[str] = []
        missing: list[str] = []
        slot_matches: list[dict] = []
        deductions: list[dict] = []
        score_sum = 0.0
        for item in required:
            match = slots_match(item.text, ocr_texts, threshold)
            match["required"] = item.text
            match["component_id"] = item.component_id
            slot_matches.append(match)
            score_sum += float(match["score"])
            if match["status"] == "pass":
                matched.append(item.text)
            elif match["status"] in {"weak_pass", "numeric_pass"}:
                weak_matched.append(item.text)
                if match["status"] == "weak_pass":
                    deductions.append(
                        deduction(
                            "information.unit_weak_match",
                            "low",
                            3,
                            f"DSL='{item.text}', OCR best='{match.get('best_text', '')}', missing_units={match.get('missing_units', [])}",
                            item.component_id,
                        )
                    )
            else:
                missing.append(item.text)
                code = "information.number_mismatch" if match.get("numbers") else "information.text_missing"
                severity = "high" if code == "information.number_mismatch" else "medium"
                # number_mismatch 幅度 = 该文本内缺失数字占比；text_missing 幅度在循环后
                # 统一设为样本级缺失率 missing_count / required_count。
                magnitude = None
                if code == "information.number_mismatch" and match.get("numbers"):
                    missing_numbers = match.get("missing_numbers") or match["numbers"]
                    magnitude = len(missing_numbers) / len(match["numbers"])
                deductions.append(
                    deduction(
                        code,
                        severity,
                        8 if severity == "high" else 6,
                        f"DSL='{item.text}', best OCR='{match.get('best_text', '')}', similarity={match.get('similarity', 0)}",
                        item.component_id,
                        magnitude=magnitude,
                    )
                )
        coverage = score_sum / len(required)
        # text_missing 幅度 = 样本级文本缺失率（missing_count / required_count）。
        missing_rate = len(missing) / len(required) if required else 0.0
        for item in deductions:
            if item["code"] == "information.text_missing":
                item["magnitude"] = round(clamp(missing_rate, 0.0, 1.0), 4)
        return MetricResult(
            name=self.name,
            dimension=self.dimension,
            score=round(coverage * 100, 2),
            value=round(coverage, 4),
            ideal=1.0,
            deviation=round(1.0 - coverage, 4),
            formula="score = 100 * coverage",
            confidence=context.vision.confidence,
            details={
                "matched": matched,
                "weak_matched": weak_matched,
                "missing": missing,
                "required_count": len(required),
                "slot_matches": slot_matches,
                "deductions": deductions,
            },
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
