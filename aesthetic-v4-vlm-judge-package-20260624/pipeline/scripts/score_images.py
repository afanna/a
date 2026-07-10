#!/usr/bin/env python3
"""Score rendered screenshots with a pluggable visual judge.

Backends:
- mock: deterministic smoke-test backend. Not an aesthetic judge.
- command: runs a trusted local command that reads request JSON on stdin and
  writes response JSON on stdout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_rubric_judge import (
    OCCLUSION_OVERLAP_CHECK,
    build_occlusion_score_impact,
    normalize_designer_review,
    normalize_occlusion_findings,
)
from aesthetic_contract import (
    AESTHETIC_PROFILE,
    INTERNAL_RUBRIC as AESTHETIC_RUBRIC,
    RUBRIC,
    RUBRIC_VERSION,
    SCORE_MAX,
    SCORE_SCALE,
    clamp_score as contract_clamp_score,
    score_to_100,
)


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_ROOT = Path(__file__).resolve().parents[1]

CACHE_LOCK = threading.Lock()

VIEWPORT_SELECTION_CHOICES = ("auto", "all", "desktop", "mobile")
ADAPTIVE_VIEWPORTS_CHOICES = ("off", "on", "auto")
SCORE_BREAKDOWN_CHOICES = ("off", "on")
DESIGNER_REVIEW_CHOICES = ("off", "on")
QUALITY_SWITCH_DEFAULTS = {
    "adaptive_viewports": "on",
    "score_breakdown": "on",
    "designer_review": "on",
    "occlusion_overlap_check": OCCLUSION_OVERLAP_CHECK,
}
DIRECT_VIEWPORT_FIELDS = (
    "target_viewport",
    "target_surface",
    "canonical_viewport",
    "canonical_surface",
    "viewport_profile",
    "ui_type",
)
QUERY_FIELDS = (
    "query",
    "query_text",
    "prompt",
    "instruction",
    "task",
    "description",
    "title",
    "layout",
    "task_group",
    "ui_type",
)
MOBILE_STRONG_HINTS = (
    "手机h5",
    "移动端",
    "手机端",
    "小程序",
    "iphone",
    "android",
    "安卓",
    "ios",
    "手机应用",
    "移动应用",
    "底部导航",
    "tab bar",
    "tabbar",
    "竖屏",
    "灵动岛",
)
MOBILE_WEAK_HINTS = ("mobile", "phone", "手机", "h5", "q_scene")
DESKTOP_STRONG_HINTS = (
    "官网",
    "网页",
    "网站",
    "web",
    "browser",
    "desktop",
    "pc端",
    "电脑端",
    "管理后台",
    "控制台",
    "dashboard",
    "仪表盘",
    "landing page",
)
DESKTOP_WEAK_HINTS = ("pc", "电脑", "桌面")
DUAL_HINTS = (
    "手机和电脑",
    "电脑和手机",
    "手机与电脑",
    "电脑与手机",
    "pc和手机",
    "手机和pc",
    "pc端和手机端",
    "手机端和pc端",
    "移动端和桌面",
    "桌面和移动端",
    "web和移动端",
    "移动端和web",
    "同时适配",
    "兼容pc",
    "兼容电脑",
    "都好用",
    "响应式",
    "responsive",
    "mobile and desktop",
    "desktop and mobile",
)
VIEWPORT_ALIASES = {
    "desktop": "desktop",
    "web": "desktop",
    "web_page": "desktop",
    "browser": "desktop",
    "pc": "desktop",
    "computer": "desktop",
    "电脑": "desktop",
    "网页": "desktop",
    "官网": "desktop",
    "mobile": "mobile",
    "mobile_app": "mobile",
    "phone": "mobile",
    "iphone": "mobile",
    "android": "mobile",
    "ios": "mobile",
    "app": "mobile",
    "h5": "mobile",
    "手机": "mobile",
    "移动端": "mobile",
    "image": "image",
    "both": "all",
    "dual": "all",
    "all": "all",
}


@dataclass
class ImageScore:
    score: float
    axis_scores: dict[str, float]
    rationale: str
    backend_meta: dict[str, Any]
    occlusion_overlap_check: str = OCCLUSION_OVERLAP_CHECK
    occlusion_findings: list[dict[str, Any]] = field(default_factory=list)
    occlusion_score_impact: dict[str, Any] = field(default_factory=dict)
    designer_review: dict[str, list[str]] | None = None
    cache_hit: bool = False
    elapsed_ms: int | None = None


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def write_jsonl(records: list[dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def append_jsonl(record: dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def round_score(value: float) -> float:
    return contract_clamp_score(value)


def anchors_hash(anchors: list[dict[str, Any]]) -> str:
    compact = json.dumps(anchors, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(compact.encode("utf-8")).hexdigest()


def normalize_on_off(value: Any, default: str) -> str:
    normalized = str(value or default).strip().lower()
    return normalized if normalized in SCORE_BREAKDOWN_CHOICES else default


def resolve_quality_config(args: argparse.Namespace) -> dict[str, str]:
    adaptive = str(
        getattr(args, "adaptive_viewports", None)
        or os.environ.get("AESTHETIC_V4_ADAPTIVE_VIEWPORTS")
        or QUALITY_SWITCH_DEFAULTS["adaptive_viewports"]
    ).strip().lower()
    if adaptive not in ADAPTIVE_VIEWPORTS_CHOICES:
        adaptive = QUALITY_SWITCH_DEFAULTS["adaptive_viewports"]
    return {
        "adaptive_viewports": adaptive,
        "score_breakdown": normalize_on_off(
            getattr(args, "score_breakdown", None)
            or os.environ.get("AESTHETIC_V4_SCORE_BREAKDOWN"),
            QUALITY_SWITCH_DEFAULTS["score_breakdown"],
        ),
        "designer_review": normalize_on_off(
            getattr(args, "designer_review", None)
            or os.environ.get("AESTHETIC_V4_DESIGNER_REVIEW"),
            QUALITY_SWITCH_DEFAULTS["designer_review"],
        ),
        "occlusion_overlap_check": OCCLUSION_OVERLAP_CHECK,
    }


def quality_config_hash(config: dict[str, str]) -> str:
    compact = json.dumps(config, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(compact.encode("utf-8")).hexdigest()


def sanitize_public_rationale(value: Any) -> str:
    text = str(value or "No rationale returned by judge.").strip()
    replacements = [
        (r"(?<![A-Za-z0-9_-])[Vv]\d+\s*所述", ""),
        (r"(?<![A-Za-z0-9_-])[Vv]\d+\s*规则", "规则"),
        (r"(?<![A-Za-z0-9_-])[Vv]\d+\s*版本", "版本"),
        (r"(?<![A-Za-z0-9_-])[Vv]\d+", ""),
        (r"Boundary stabilizers?", "boundary rules"),
        (r"prompt[_ -]?version", "prompt"),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"（\s*）|\(\s*\)", "", text)
    text = re.sub(r"属于\s+", "属于", text)
    return text.strip()


def weighted_contributions(axis_scores: dict[str, float]) -> dict[str, dict[str, float]]:
    contributions: dict[str, dict[str, float]] = {}
    for axis, weight in RUBRIC["weights"].items():
        value = round_score(axis_scores.get(axis, 0.0))
        contributions[axis] = {
            "score": value,
            "weight": float(weight),
            "weighted_contribution": round(value * float(weight), 3),
        }
    return contributions


def weighted_scores(axis_scores: dict[str, float]) -> dict[str, float]:
    return {
        axis: round(round_score(axis_scores.get(axis, 0.0)) * float(weight), 3)
        for axis, weight in RUBRIC["weights"].items()
    }


def score_100(score: float | None) -> float | None:
    return score_to_100(score)


OCCLUSION_SEVERITY_RANK = {
    "none": 0,
    "minor": 1,
    "moderate": 2,
    "severe": 3,
    "blocking": 4,
}


def dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        item = str(value).strip()
        if item and item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def occlusion_overlap_summary(findings: list[dict[str, Any]] | None) -> dict[str, Any]:
    normalized = [finding for finding in (findings or []) if isinstance(finding, dict)]
    highest_status = "none"
    types: list[str] = []
    affected_axes: list[str] = []
    targets: list[str] = []
    evidence: list[str] = []

    for finding in normalized:
        severity = str(finding.get("severity") or "").strip().lower()
        if OCCLUSION_SEVERITY_RANK.get(severity, -1) > OCCLUSION_SEVERITY_RANK[highest_status]:
            highest_status = severity

        finding_type = str(finding.get("type") or "").strip()
        if finding_type:
            types.append(finding_type)

        axes = finding.get("affected_axes")
        if isinstance(axes, list):
            affected_axes.extend(str(axis).strip() for axis in axes if str(axis).strip() in RUBRIC["weights"])

        target = str(finding.get("target") or "").strip()
        if target:
            targets.append(target)

        evidence_text = str(finding.get("evidence") or "").strip()
        if evidence_text:
            evidence.append(evidence_text)

    return {
        "detected": bool(normalized),
        "status": highest_status,
        "highest_severity": highest_status,
        "count": len(normalized),
        "types": dedupe_strings(types),
        "affected_axes": dedupe_strings(affected_axes),
        "targets": dedupe_strings(targets)[:5],
        "evidence": dedupe_strings(evidence)[:5],
    }


def occlusion_overlap_marker_fields(findings: list[dict[str, Any]] | None) -> dict[str, Any]:
    summary = occlusion_overlap_summary(findings)
    return {
        "occlusion_overlap_detected": summary["detected"],
        "occlusion_overlap_status": summary["status"],
        "occlusion_overlap_types": summary["types"],
        "occlusion_overlap_affected_axes": summary["affected_axes"],
        "occlusion_overlap_issue": summary,
    }


def empty_axis_scores() -> dict[str, None]:
    return {axis: None for axis in RUBRIC["weights"]}


def average_axis_scores(view_scores: dict[str, ImageScore]) -> dict[str, float]:
    averaged: dict[str, float] = {}
    for axis in RUBRIC["weights"]:
        values = [score.axis_scores.get(axis, 0.0) for score in view_scores.values()]
        averaged[axis] = round_score(sum(values) / len(values)) if values else 0.0
    return averaged


def view_extra_aesthetics(score: ImageScore, *, include_designer_review: bool) -> dict[str, Any]:
    weights = weighted_scores(score.axis_scores)
    weighted_total = round(sum(weights.values()), 3)
    final = round_score(weighted_total)
    return {
        "score": final,
        "score_100": score_100(final),
        "axis_scores": score.axis_scores,
        "weighted_scores": weights,
        "weighted_total": weighted_total,
        "occlusion_overlap_check": score.occlusion_overlap_check,
        **occlusion_overlap_marker_fields(score.occlusion_findings),
        "designer_review": score.designer_review if include_designer_review else None,
    }


def build_extra_info_scores(
    *,
    status: str,
    final_score: float | None,
    aggregate_view: str | None,
    aggregate_formula: str,
    view_scores: dict[str, ImageScore],
    quality_config: dict[str, str],
) -> dict[str, Any]:
    aggregate_score = view_scores.get(aggregate_view) if aggregate_view else None
    include_designer_review = quality_config.get("designer_review") == "on"
    if aggregate_score is not None:
        axis_scores = aggregate_score.axis_scores
        designer_review = aggregate_score.designer_review if include_designer_review else None
        findings = aggregate_score.occlusion_findings
    elif view_scores:
        axis_scores = average_axis_scores(view_scores)
        designer_review = None
        findings = [
            finding
            for score in view_scores.values()
            for finding in score.occlusion_findings
        ]
    else:
        axis_scores = empty_axis_scores()
        designer_review = None
        findings = []

    if final_score is None:
        weighted = empty_axis_scores()
        weighted_total = None
        aesthetics_score = None
        aesthetics_status = "failed"
    else:
        weighted = weighted_scores(axis_scores)  # type: ignore[arg-type]
        weighted_total = round(sum(weighted.values()), 3)
        aesthetics_score = round_score(weighted_total)
        aesthetics_status = "success" if status == "scored" else status

    aesthetics: dict[str, Any] = {
        "profile": AESTHETIC_PROFILE,
        "score": aesthetics_score,
        "score_100": score_100(aesthetics_score),
        "status": aesthetics_status,
        "rubric_version": RUBRIC_VERSION,
        "score_scale": "0-8",
        "adaptive_viewports": quality_config.get("adaptive_viewports"),
        "aggregate_strategy": "min_score" if aggregate_formula.startswith("min_") else aggregate_formula,
        "aggregate_view": aggregate_view,
        "axis_scores": axis_scores,
        "weighted_scores": weighted,
        "weighted_total": weighted_total,
        "occlusion_overlap_check": OCCLUSION_OVERLAP_CHECK,
        **occlusion_overlap_marker_fields(findings),
        "designer_review": designer_review,
    }
    if quality_config.get("adaptive_viewports") in {"on", "auto"} and len(view_scores) > 1:
        aesthetics["views"] = {
            viewport: view_extra_aesthetics(score, include_designer_review=include_designer_review)
            for viewport, score in view_scores.items()
        }
    return {"aesthetics": aesthetics}


def score_breakdown_for_views(
    view_scores: dict[str, ImageScore],
    *,
    final_score: float | None,
    aggregate_view: str | None,
) -> dict[str, Any]:
    return {
        "final_score": final_score,
        "aggregate_view": aggregate_view,
        "rubric_weights": RUBRIC["weights"],
        "views": {
            viewport: {
                "score": score.score,
                "axis_scores": score.axis_scores,
                "weighted_contributions": weighted_contributions(score.axis_scores),
                "occlusion_findings": score.occlusion_findings,
                "occlusion_score_impact": score.occlusion_score_impact,
                **occlusion_overlap_marker_fields(score.occlusion_findings),
            }
            for viewport, score in view_scores.items()
        },
    }


def load_cache(cache_path: Path) -> dict[str, dict[str, Any]]:
    cache: dict[str, dict[str, Any]] = {}
    for record in read_jsonl(cache_path):
        key = record.get("cache_key")
        if isinstance(key, str):
            cache[key] = record
    return cache


def normalize_backend_result(
    payload: dict[str, Any],
    quality_config: dict[str, str] | None = None,
) -> ImageScore:
    if "score" not in payload:
        raise ValueError("judge response must include score")
    axis_scores = payload.get("axis_scores")
    if not isinstance(axis_scores, dict):
        axis_scores = {}
    raw_score = round_score(payload["score"])
    normalized_axis = {
        axis: round_score(axis_scores.get(axis, raw_score))
        for axis in RUBRIC["weights"]
    }
    score = round_score(sum(weighted_scores(normalized_axis).values()))
    rationale = sanitize_public_rationale(payload.get("rationale"))
    findings = normalize_occlusion_findings(
        payload,
        rationale=rationale,
        axis_scores=normalized_axis,
        score=raw_score,
    )
    impact = payload.get("occlusion_score_impact")
    if not isinstance(impact, dict) or not impact.get("affected_axes") and findings:
        impact = build_occlusion_score_impact(normalized_axis, findings)
    designer_review = normalize_designer_review(payload.get("designer_review"))
    if (quality_config or {}).get("designer_review") != "on":
        designer_review = None
    return ImageScore(
        score=score,
        axis_scores=normalized_axis,
        rationale=rationale,
        occlusion_overlap_check=str(payload.get("occlusion_overlap_check") or OCCLUSION_OVERLAP_CHECK),
        occlusion_findings=findings,
        occlusion_score_impact=impact,
        designer_review=designer_review,
        backend_meta=dict(payload.get("backend_meta") or {}),
    )


def mock_score(image: dict[str, Any]) -> ImageScore:
    digest = image["sha256"]
    raw = int(digest[:12], 16) / float(0xFFFFFFFFFFFF)
    score = round_score(raw * SCORE_MAX)
    axis = {
        "visual_impact_originality": score,
        "composition_hierarchy": round_score(score * 0.95),
        "typography": round_score(score * 0.9),
        "color_material": round_score(score * 1.02),
        "detail_finish": round_score(score * 0.92),
        "basic_usability": round_score(score * 0.85),
    }
    return ImageScore(
        score=score,
        axis_scores=axis,
        rationale=(
            "Deterministic mock score for pipeline validation only; "
            "do not treat this as an aesthetic judgment."
        ),
        designer_review={
            "pros": ["mock backend: pipeline structure and JSON export are reachable"],
            "cons": ["mock backend does not evaluate real visual quality"],
            "suggestions": ["run with a configured model backend for real designer review"],
        },
        occlusion_findings=[],
        occlusion_score_impact=build_occlusion_score_impact(axis, []),
        backend_meta={"mock": True},
    )


def command_score(
    image: dict[str, Any],
    anchors: list[dict[str, Any]],
    command: str,
    timeout: int,
    quality_config: dict[str, str],
) -> ImageScore:
    request = {
        "schema_version": 1,
        "rubric_version": RUBRIC_VERSION,
        "rubric": RUBRIC,
        "quality_config": quality_config,
        "anchors": blind_anchor_payload(anchors),
        "image": image,
        "required_response_schema": {
            "score": "number from 0 to 8, one decimal preferred",
            "axis_scores": "object with rubric axis scores from 0 to 8",
            "rationale": "short reason grounded in visible design evidence",
            "occlusion_overlap_check": "always_on",
            "occlusion_findings": "array; empty when no overlap/occlusion is visible",
            "occlusion_score_impact": "fixed-weight impact derived from affected axis_scores",
            "designer_review": "optional object only when quality_config.designer_review is on",
            "backend_meta": "optional object",
        },
    }
    proc = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(
            input=json.dumps(request, ensure_ascii=False),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except Exception:
            proc.kill()
        proc.communicate()
        raise TimeoutError(f"judge command timed out after {timeout} seconds") from exc

    if proc.returncode != 0:
        raise RuntimeError(
            f"judge command failed with code {proc.returncode}: {stderr.strip()}"
        )
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"judge command returned non-JSON stdout: {stdout[:500]}") from exc
    result = normalize_backend_result(payload, quality_config=quality_config)
    result.backend_meta["command"] = command
    return result


def blind_anchor_payload(anchors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blind: list[dict[str, Any]] = []
    for anchor in anchors:
        image_path = anchor.get("image_path") or anchor.get("screenshot_path")
        score = anchor.get("score")
        if image_path is None or score is None:
            continue
        item = {
            "anchor_id": anchor.get("anchor_id") or anchor.get("id"),
            "score": round_score(score),
            "image_path": str(Path(image_path).resolve()),
        }
        try:
            item["image_sha256"] = sha256_file(Path(image_path))
        except Exception:
            item["image_sha256"] = anchor.get("image_sha256")
        blind.append(item)
    return blind


def cache_key_for(
    image_sha256: str,
    backend: str,
    anchor_digest: str,
    backend_identity: str,
    quality_digest: str,
) -> str:
    parts = [RUBRIC_VERSION, backend, backend_identity, anchor_digest, quality_digest, image_sha256]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def score_image(
    image: dict[str, Any],
    backend: str,
    anchors: list[dict[str, Any]],
    cache: dict[str, dict[str, Any]],
    cache_path: Path,
    refresh: bool,
    judge_command: str | None,
    timeout: int,
    quality_config: dict[str, str],
) -> ImageScore:
    started = time.perf_counter()
    anchor_digest = anchors_hash(blind_anchor_payload(anchors))
    backend_identity = judge_command or "builtin"
    quality_digest = quality_config_hash(quality_config)
    key = cache_key_for(image["sha256"], backend, anchor_digest, backend_identity, quality_digest)
    with CACHE_LOCK:
        cached_record = cache.get(key)
    if not refresh and cached_record is not None:
        cached = normalize_backend_result(cached_record["result"], quality_config=quality_config)
        cached.cache_hit = True
        cached.elapsed_ms = int((time.perf_counter() - started) * 1000)
        return cached

    if backend == "mock":
        result = mock_score(image)
    elif backend == "command":
        if not judge_command:
            raise RuntimeError(
                "command backend requires --judge-command or AESTHETIC_JUDGE_COMMAND"
            )
        result = command_score(image, anchors, judge_command, timeout, quality_config)
    else:
        raise RuntimeError(f"unsupported backend: {backend}")

    result.elapsed_ms = int((time.perf_counter() - started) * 1000)
    cache_record = {
        "cache_key": key,
        "rubric_version": RUBRIC_VERSION,
        "backend": backend,
        "backend_identity": backend_identity,
        "anchor_digest": anchor_digest,
        "quality_config": quality_config,
        "quality_digest": quality_digest,
        "image_sha256": image["sha256"],
        "result": {
            "score": result.score,
            "axis_scores": result.axis_scores,
            "rationale": result.rationale,
            "occlusion_overlap_check": result.occlusion_overlap_check,
            "occlusion_findings": result.occlusion_findings,
            "occlusion_score_impact": result.occlusion_score_impact,
            "designer_review": result.designer_review,
            "backend_meta": result.backend_meta,
        },
        "elapsed_ms": result.elapsed_ms,
    }
    with CACHE_LOCK:
        append_jsonl(cache_record, cache_path)
        cache[key] = cache_record
    return result


def load_input_records(input_path: Path) -> list[dict[str, Any]]:
    if input_path.suffix.lower() in {".jsonl", ".json"}:
        if input_path.suffix.lower() == ".json":
            payload = json.loads(input_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, list) else [payload]
        return read_jsonl(input_path)
    digest = sha256_file(input_path)
    return [
        {
            "id": input_path.stem,
            "source": "direct",
            "source_key": "direct",
            "input_type": "image",
            "input_path": str(input_path.resolve()),
            "render_status": "ok",
            "views": [
                {
                    "viewport": "image",
                    "status": "ok",
                    "screenshot_path": str(input_path.resolve()),
                    "screenshot_sha256": digest,
                }
            ],
        }
    ]


def normalize_viewport_value(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().casefold()
    if not normalized:
        return None
    normalized = normalized.replace("-", "_").replace(" ", "_")
    return VIEWPORT_ALIASES.get(normalized)


def read_sidecar_metadata(input_path: Any) -> dict[str, Any]:
    if not isinstance(input_path, str) or not input_path:
        return {}
    path = Path(input_path)
    candidates = [
        path.with_suffix(".meta.json"),
        path.parent / "query_instruction.json",
        path.parent / "metadata.json",
    ]
    for candidate in candidates:
        if not candidate.exists() or not candidate.is_file():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def collect_text_values(mapping: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    values: list[str] = []
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    return values


def query_context_text(record: dict[str, Any], views: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    parts.extend(collect_text_values(record, QUERY_FIELDS))
    parts.extend(collect_text_values(record, ("id", "sample_relpath", "input_path", "input_type")))
    sample_metadata = record.get("sample_metadata")
    if isinstance(sample_metadata, dict):
        parts.extend(collect_text_values(sample_metadata, QUERY_FIELDS))
    sidecar = read_sidecar_metadata(record.get("input_path"))
    if sidecar:
        parts.extend(collect_text_values(sidecar, QUERY_FIELDS))
    for view in views:
        page_metrics = view.get("page_metrics")
        if isinstance(page_metrics, dict):
            title = page_metrics.get("title")
            if isinstance(title, str) and title.strip():
                parts.append(title.strip())
    return " ".join(parts).casefold()


def explicit_viewport_from_record(record: dict[str, Any]) -> tuple[str | None, str | None]:
    for key in DIRECT_VIEWPORT_FIELDS:
        viewport = normalize_viewport_value(record.get(key))
        if viewport:
            return viewport, f"record.{key}"
    sample_metadata = record.get("sample_metadata")
    if isinstance(sample_metadata, dict):
        for key in DIRECT_VIEWPORT_FIELDS:
            viewport = normalize_viewport_value(sample_metadata.get(key))
            if viewport:
                return viewport, f"sample_metadata.{key}"
    sidecar = read_sidecar_metadata(record.get("input_path"))
    for key in DIRECT_VIEWPORT_FIELDS:
        viewport = normalize_viewport_value(sidecar.get(key))
        if viewport:
            return viewport, f"sidecar.{key}"
    return None, None


def infer_viewport_from_query(record: dict[str, Any], views: list[dict[str, Any]]) -> tuple[str, str, str | None]:
    explicit, source = explicit_viewport_from_record(record)
    if explicit and explicit != "all":
        return explicit, source or "record", None

    text = query_context_text(record, views)
    has_dual = any(token in text for token in DUAL_HINTS)
    has_mobile_strong = any(token in text for token in MOBILE_STRONG_HINTS)
    has_desktop_strong = any(token in text for token in DESKTOP_STRONG_HINTS) or bool(
        re.search(r"\.(com|co\.uk|studio|care|design)\b", text)
    )
    has_app_concept = bool(re.search(r"\bapp\b", text)) or "应用" in text
    has_mobile = (
        has_mobile_strong
        or any(token in text for token in MOBILE_WEAK_HINTS)
        or (has_app_concept and not has_desktop_strong)
    )
    has_desktop = has_desktop_strong or any(token in text for token in DESKTOP_WEAK_HINTS)

    if explicit == "all":
        if has_mobile and not has_desktop:
            return "mobile", source or "record.all_tiebreak", "explicit_all_reduced_to_mobile"
        if has_desktop_strong and not has_mobile_strong:
            return "desktop", source or "record.all_tiebreak", "explicit_all_reduced_to_desktop"
        return "desktop", source or "record.all_tiebreak", "explicit_all_reduced_to_desktop_default"

    if has_dual:
        if has_mobile and not has_desktop:
            return "mobile", "query.strong_mobile", "dual_text_reduced_to_mobile"
        if has_desktop_strong and not has_mobile_strong:
            return "desktop", "query.strong_desktop", "dual_text_reduced_to_desktop"
        return "desktop", "query.dual", "dual_text_reduced_to_desktop_default"
    if has_mobile and not has_desktop:
        return "mobile", "query.mobile_hint", None
    if has_desktop and not has_mobile:
        return "desktop", "query.desktop_hint", None
    if has_mobile_strong:
        return "mobile", "query.strong_mobile", None
    return "desktop", "default.desktop", None


def standard_viewport_names(views: list[dict[str, Any]]) -> set[str]:
    return {str(view.get("viewport") or "") for view in views if str(view.get("viewport") or "") in {"desktop", "mobile"}}


def has_dual_viewport_risk(record: dict[str, Any], views: list[dict[str, Any]]) -> bool:
    names = standard_viewport_names(views)
    if not {"desktop", "mobile"}.issubset(names):
        return False
    explicit, _source = explicit_viewport_from_record(record)
    if explicit == "all":
        return True
    text = query_context_text(record, views)
    return any(token in text for token in DUAL_HINTS)


def choose_scoring_views(
    record: dict[str, Any],
    views: list[dict[str, Any]],
    viewport_selection: str,
    adaptive_viewports: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    available = [str(view.get("viewport") or "image") for view in views]
    if available == ["image"]:
        return views, {
            "viewport_selection": viewport_selection,
            "adaptive_viewports": adaptive_viewports,
            "adaptive_viewports_reasons": ["single_image_input"],
            "target_viewport": "image",
            "target_viewport_source": "single_image_input",
            "target_viewport_note": None,
            "target_viewport_fallback": None,
            "available_viewports": available,
            "scored_viewports": available,
        }
    if adaptive_viewports == "on":
        return views, {
            "viewport_selection": "all",
            "adaptive_viewports": "on",
            "adaptive_viewports_reasons": ["adaptive_viewports.on"],
            "target_viewport": "all",
            "target_viewport_source": "adaptive_viewports.on",
            "target_viewport_note": "desktop_mobile_min_score",
            "target_viewport_fallback": None,
            "available_viewports": available,
            "scored_viewports": available,
        }
    if adaptive_viewports == "off" and viewport_selection == "all":
        viewport_selection = "auto"
    if viewport_selection == "all":
        return views, {
            "viewport_selection": "all",
            "adaptive_viewports": adaptive_viewports,
            "adaptive_viewports_reasons": ["cli.all"],
            "target_viewport": "all",
            "target_viewport_source": "cli.all",
            "target_viewport_note": None,
            "target_viewport_fallback": None,
            "available_viewports": available,
            "scored_viewports": available,
        }
    if adaptive_viewports == "auto" and viewport_selection == "auto" and has_dual_viewport_risk(record, views):
        return views, {
            "viewport_selection": "all",
            "adaptive_viewports": "auto",
            "adaptive_viewports_reasons": ["responsive_or_dual_viewport_risk"],
            "target_viewport": "all",
            "target_viewport_source": "adaptive_viewports.auto",
            "target_viewport_note": "responsive_or_dual_viewport_risk",
            "target_viewport_fallback": None,
            "available_viewports": available,
            "scored_viewports": available,
        }

    target = viewport_selection
    source = f"cli.{viewport_selection}"
    note = None
    if viewport_selection == "auto":
        target, source, note = infer_viewport_from_query(record, views)

    if target == "image":
        selected = [view for view in views if str(view.get("viewport") or "image") == "image"]
    else:
        selected = [view for view in views if str(view.get("viewport") or "") == target]

    fallback = None
    if not selected and views:
        selected = views[:1]
        fallback = f"target_viewport_missing_used_{str(selected[0].get('viewport') or 'image')}"

    metadata = {
        "viewport_selection": viewport_selection,
        "adaptive_viewports": adaptive_viewports,
        "adaptive_viewports_reasons": [],
        "target_viewport": target,
        "target_viewport_source": source,
        "target_viewport_note": note,
        "target_viewport_fallback": fallback,
        "available_viewports": available,
        "scored_viewports": [str(view.get("viewport") or "image") for view in selected],
    }
    return selected, metadata


def score_near_bucket_threshold(score: float) -> bool:
    score_100 = score * 12.5
    return any(abs(score_100 - boundary) <= 3.0 for boundary in (10, 20, 30, 40, 50, 60, 70, 80))


def low_confidence_score(score: ImageScore) -> bool:
    confidence = score.backend_meta.get("confidence")
    if isinstance(confidence, (int, float)) and float(confidence) <= 0.55:
        return True
    text = score.rationale.casefold()
    return any(token in text for token in ("无法确认", "不确定", "难以判断", "看不清", "uncertain"))


def occlusion_risk_score(score: ImageScore) -> bool:
    for finding in score.occlusion_findings:
        if str(finding.get("severity")) in {"severe", "blocking"}:
            return True
    return False


def adaptive_auto_extend_reasons(
    record: dict[str, Any],
    all_views: list[dict[str, Any]],
    view_scores: dict[str, ImageScore],
    args: argparse.Namespace,
) -> list[str]:
    if not view_scores or not {"desktop", "mobile"}.issubset(standard_viewport_names(all_views)):
        return []
    reasons: list[str] = []
    if bool(getattr(args, "formal_report", False)):
        reasons.append("formal_report")
    if has_dual_viewport_risk(record, all_views):
        reasons.append("responsive_or_dual_viewport_risk")
    for score in view_scores.values():
        if low_confidence_score(score):
            reasons.append("low_confidence")
        if score_near_bucket_threshold(score.score):
            reasons.append("near_score_threshold")
        if occlusion_risk_score(score):
            reasons.append("occlusion_or_overlap_risk")
    return sorted(set(reasons))


def image_payload(record: dict[str, Any], view: dict[str, Any]) -> dict[str, Any]:
    path_value = view.get("screenshot_path")
    if not path_value:
        raise ValueError("view missing screenshot_path")
    image_path = Path(path_value)
    digest = view.get("screenshot_sha256") or sha256_file(image_path)
    return {
        "sample_id": record.get("id"),
        "viewport": view.get("viewport"),
        "path": str(image_path.resolve()),
        "sha256": digest,
        "width": view.get("screenshot_width"),
        "height": view.get("screenshot_height"),
    }


def aggregate_scores(
    record: dict[str, Any], view_scores: dict[str, ImageScore], strategy: str
) -> tuple[float | None, str, str | None]:
    if len(view_scores) == 1:
        viewport, only = next(iter(view_scores.items()))
        return only.score, "single_canonical_screenshot_score", viewport
    if len(view_scores) > 1:
        if strategy == "min":
            viewport, score = min(view_scores.items(), key=lambda item: item[1].score)
            return score.score, "min_of_available_views", viewport
        values = [score.score for score in view_scores.values()]
        return round_score(sum(values) / len(values)), "mean_of_available_views", None
    return None, "not_scored", None


def score_record(
    record: dict[str, Any],
    args: argparse.Namespace,
    anchors: list[dict[str, Any]],
    cache: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    record_started = time.perf_counter()
    quality_config = resolve_quality_config(args)
    all_views = [view for view in record.get("views", []) if view.get("status") == "ok"]
    views, viewport_metadata = choose_scoring_views(
        record,
        all_views,
        getattr(args, "viewport_selection", "auto"),
        quality_config["adaptive_viewports"],
    )
    if not views:
        return {
            "schema_version": 1,
            "profile": AESTHETIC_PROFILE,
            "rubric_version": RUBRIC_VERSION,
            "aesthetic_rubric": AESTHETIC_RUBRIC,
            "id": record.get("id"),
            "source": record.get("source"),
            "source_key": record.get("source_key"),
            "source_score_prior": record.get("source_score_prior"),
            "input_path": record.get("input_path"),
            "sample_relpath": record.get("sample_relpath"),
            "sample_metadata": record.get("sample_metadata") or {},
            "status": "failed",
            "final_score": None,
            "rationale": "No successful rendered screenshots available.",
            "quality_config": quality_config,
            "extra_info_scores": build_extra_info_scores(
                status="failed",
                final_score=None,
                aggregate_view=None,
                aggregate_formula="not_scored",
                view_scores={},
                quality_config=quality_config,
            ),
            "occlusion_overlap_check": OCCLUSION_OVERLAP_CHECK,
            "occlusion_findings": [],
            "occlusion_score_impact": build_occlusion_score_impact({}, []),
            **occlusion_overlap_marker_fields([]),
            "render_status": record.get("render_status"),
            "render_errors": record.get("render_errors", []),
            **viewport_metadata,
            "timing": {
                "record_elapsed_ms": int((time.perf_counter() - record_started) * 1000),
                "available_view_count": len(all_views),
                "view_count": 0,
                "scored_view_count": 0,
            },
        }

    view_scores: dict[str, ImageScore] = {}
    view_payloads: dict[str, dict[str, Any]] = {}
    view_timings: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    for view in views:
        viewport = str(view.get("viewport") or "image")
        view_started = time.perf_counter()
        try:
            image = image_payload(record, view)
            view_payloads[viewport] = image
            view_scores[viewport] = score_image(
                image=image,
                backend=args.backend,
                anchors=anchors,
                cache=cache,
                cache_path=Path(args.cache),
                refresh=args.refresh,
                judge_command=args.judge_command or os.environ.get("AESTHETIC_JUDGE_COMMAND"),
                timeout=args.timeout,
                quality_config=quality_config,
            )
            view_timings[viewport] = {
                "elapsed_ms": view_scores[viewport].elapsed_ms,
                "cache_hit": view_scores[viewport].cache_hit,
            }
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - view_started) * 1000)
            view_timings[viewport] = {
                "elapsed_ms": elapsed_ms,
                "cache_hit": False,
                "failed": True,
            }
            errors.append({"viewport": viewport, "error": str(exc), "elapsed_ms": elapsed_ms})

    if quality_config["adaptive_viewports"] == "auto":
        extend_reasons = adaptive_auto_extend_reasons(record, all_views, view_scores, args)
        scored_names = set(view_scores)
        remaining_views = [
            view
            for view in all_views
            if str(view.get("viewport") or "image") not in scored_names
        ]
        if extend_reasons and remaining_views:
            viewport_metadata["adaptive_viewports_reasons"] = sorted(
                set(viewport_metadata.get("adaptive_viewports_reasons", []) + extend_reasons)
            )
            viewport_metadata["target_viewport"] = "all"
            viewport_metadata["target_viewport_source"] = "adaptive_viewports.auto"
            viewport_metadata["target_viewport_note"] = ",".join(viewport_metadata["adaptive_viewports_reasons"])
            for view in remaining_views:
                viewport = str(view.get("viewport") or "image")
                view_started = time.perf_counter()
                try:
                    image = image_payload(record, view)
                    view_payloads[viewport] = image
                    view_scores[viewport] = score_image(
                        image=image,
                        backend=args.backend,
                        anchors=anchors,
                        cache=cache,
                        cache_path=Path(args.cache),
                        refresh=args.refresh,
                        judge_command=args.judge_command or os.environ.get("AESTHETIC_JUDGE_COMMAND"),
                        timeout=args.timeout,
                        quality_config=quality_config,
                    )
                    view_timings[viewport] = {
                        "elapsed_ms": view_scores[viewport].elapsed_ms,
                        "cache_hit": view_scores[viewport].cache_hit,
                    }
                except Exception as exc:
                    elapsed_ms = int((time.perf_counter() - view_started) * 1000)
                    view_timings[viewport] = {
                        "elapsed_ms": elapsed_ms,
                        "cache_hit": False,
                        "failed": True,
                    }
                    errors.append({"viewport": viewport, "error": str(exc), "elapsed_ms": elapsed_ms})

    viewport_metadata["scored_viewports"] = list(view_scores)
    aggregate_strategy = args.aggregate_strategy
    if quality_config["adaptive_viewports"] in {"on", "auto"} and len(view_scores) > 1:
        aggregate_strategy = "min"
    final_score, formula, aggregate_view = aggregate_scores(record, view_scores, aggregate_strategy)
    status = "scored" if final_score is not None and not errors else "partial"
    if final_score is None:
        status = "partial" if view_scores else "failed"
    aggregate_score = view_scores.get(aggregate_view) if aggregate_view else None
    top_level_findings = aggregate_score.occlusion_findings if aggregate_score else [
        finding
        for score in view_scores.values()
        for finding in score.occlusion_findings
    ]
    top_level_impact = (
        aggregate_score.occlusion_score_impact
        if aggregate_score
        else build_occlusion_score_impact({}, top_level_findings)
    )

    result = {
        "schema_version": 1,
        "profile": AESTHETIC_PROFILE,
        "rubric_version": RUBRIC_VERSION,
        "aesthetic_rubric": AESTHETIC_RUBRIC,
        "id": record.get("id"),
        "source": record.get("source"),
        "source_key": record.get("source_key"),
        "source_score_prior": record.get("source_score_prior"),
        "input_path": record.get("input_path"),
        "sample_relpath": record.get("sample_relpath"),
        "sample_metadata": record.get("sample_metadata") or {},
        "status": status,
        "backend": args.backend,
        "quality_config": quality_config,
        "occlusion_overlap_check": OCCLUSION_OVERLAP_CHECK,
        "occlusion_findings": top_level_findings,
        "occlusion_score_impact": top_level_impact,
        **occlusion_overlap_marker_fields(top_level_findings),
        "render_status": record.get("render_status"),
        "render_errors": record.get("render_errors", []),
        **viewport_metadata,
        "score_scale": SCORE_SCALE,
        "final_score": final_score,
        "aggregate_formula": formula,
        "aggregate_view": aggregate_view,
        "extra_info_scores": build_extra_info_scores(
            status=status,
            final_score=final_score,
            aggregate_view=aggregate_view,
            aggregate_formula=formula,
            view_scores=view_scores,
            quality_config=quality_config,
        ),
        "views": {
            viewport: {
                "score": score.score,
                "axis_scores": score.axis_scores,
                "rationale": score.rationale,
                "occlusion_overlap_check": score.occlusion_overlap_check,
                "occlusion_findings": score.occlusion_findings,
                "occlusion_score_impact": score.occlusion_score_impact,
                **occlusion_overlap_marker_fields(score.occlusion_findings),
                "weighted_contributions": weighted_contributions(score.axis_scores)
                if quality_config["score_breakdown"] == "on"
                else {},
                "designer_review": score.designer_review
                if quality_config["designer_review"] == "on"
                else None,
                "cache_hit": score.cache_hit,
                "elapsed_ms": score.elapsed_ms,
                "image": view_payloads.get(viewport),
                "backend_meta": score.backend_meta,
            }
            for viewport, score in view_scores.items()
        },
        "errors": errors,
        "timing": {
            "record_elapsed_ms": int((time.perf_counter() - record_started) * 1000),
            "available_view_count": len(all_views),
            "view_count": len(view_timings),
            "scored_view_count": len(view_scores),
            "views": view_timings,
        },
        "rationale": " / ".join(
            f"{viewport}: {score.rationale}" for viewport, score in view_scores.items()
        )
        or "No score rationale available.",
    }
    if quality_config["score_breakdown"] == "on":
        result["score_breakdown"] = score_breakdown_for_views(
            view_scores,
            final_score=final_score,
            aggregate_view=aggregate_view,
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Render manifest JSONL or image file.")
    parser.add_argument(
        "--out",
        default=str(PACKAGE_ROOT / "runs" / "aesthetic-v4" / "scores.jsonl"),
    )
    parser.add_argument(
        "--cache",
        default=str(PACKAGE_ROOT / "runs" / "aesthetic-v4" / "score_cache.jsonl"),
    )
    parser.add_argument("--anchors", default=str(PIPELINE_ROOT / "anchors" / "anchors.jsonl"))
    parser.add_argument("--backend", default=os.environ.get("AESTHETIC_JUDGE_BACKEND", "mock"))
    parser.add_argument("--judge-command", default=None)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--aggregate-strategy", choices=["mean", "min"], default="mean")
    parser.add_argument(
        "--viewport-selection",
        choices=VIEWPORT_SELECTION_CHOICES,
        default="auto",
        help=(
            "auto scores one canonical screenshot inferred from record/query context; "
            "all preserves legacy multi-view scoring."
        ),
    )
    parser.add_argument(
        "--adaptive-viewports",
        choices=ADAPTIVE_VIEWPORTS_CHOICES,
        default=os.environ.get("AESTHETIC_V4_ADAPTIVE_VIEWPORTS", "off"),
        help="off scores one default viewport; on scores all rendered viewports and uses min; auto adds extra viewports for responsive risk, low confidence, threshold, occlusion, or formal report runs.",
    )
    parser.add_argument(
        "--score-breakdown",
        choices=SCORE_BREAKDOWN_CHOICES,
        default=os.environ.get("AESTHETIC_V4_SCORE_BREAKDOWN", "on"),
        help="on writes weighted contributions and occlusion impact; off lets reports hide breakdown while scoring stays unchanged.",
    )
    parser.add_argument(
        "--designer-review",
        choices=DESIGNER_REVIEW_CHOICES,
        default=os.environ.get("AESTHETIC_V4_DESIGNER_REVIEW", "off"),
        help="on asks for extra designer pros/cons/suggestions; off strips long review text from output.",
    )
    parser.add_argument(
        "--formal-report",
        action="store_true",
        default=os.environ.get("AESTHETIC_V4_FORMAL_REPORT", "0") == "1",
        help="with adaptive_viewports=auto, score the alternate viewport for formal report runs.",
    )
    args = parser.parse_args()
    quality_config = resolve_quality_config(args)

    run_started_at = datetime.now(timezone.utc)
    run_started = time.perf_counter()
    input_records = load_input_records(Path(args.input))
    if args.limit > 0:
        input_records = input_records[: args.limit]
    anchors = read_jsonl(Path(args.anchors))
    cache = load_cache(Path(args.cache))

    output: list[dict[str, Any]] = []
    if args.workers <= 1:
        for record in input_records:
            scored = score_record(record, args, anchors, cache)
            output.append(scored)
            print(
                json.dumps(
                    {
                        "id": scored.get("id"),
                        "status": scored.get("status"),
                        "final_score": scored.get("final_score"),
                        "target_viewport": scored.get("target_viewport"),
                        "scored_viewports": scored.get("scored_viewports"),
                        "adaptive_viewports": scored.get("adaptive_viewports"),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    else:
        ordered: list[dict[str, Any] | None] = [None] * len(input_records)
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(score_record, record, args, anchors, cache): idx
                for idx, record in enumerate(input_records)
            }
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    scored = future.result()
                except Exception as exc:
                    record = input_records[idx]
                    scored = {
                        "schema_version": 1,
                        "profile": AESTHETIC_PROFILE,
                        "rubric_version": RUBRIC_VERSION,
                        "aesthetic_rubric": AESTHETIC_RUBRIC,
                        "id": record.get("id"),
                        "source": record.get("source"),
                        "source_key": record.get("source_key"),
                        "input_path": record.get("input_path"),
                        "sample_relpath": record.get("sample_relpath"),
                        "sample_metadata": record.get("sample_metadata") or {},
                        "status": "failed",
                        "final_score": None,
                        "rationale": f"Unhandled worker error: {exc}",
                        "extra_info_scores": build_extra_info_scores(
                            status="failed",
                            final_score=None,
                            aggregate_view=None,
                            aggregate_formula="not_scored",
                            view_scores={},
                            quality_config=quality_config,
                        ),
                        "errors": [{"error": str(exc)}],
                    }
                ordered[idx] = scored
                print(
                    json.dumps(
                        {
                            "id": scored.get("id"),
                            "status": scored.get("status"),
                            "final_score": scored.get("final_score"),
                            "target_viewport": scored.get("target_viewport"),
                            "scored_viewports": scored.get("scored_viewports"),
                            "adaptive_viewports": scored.get("adaptive_viewports"),
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
        output = [record for record in ordered if record is not None]

    write_jsonl(output, Path(args.out))
    elapsed_seconds = time.perf_counter() - run_started
    scored_count = sum(1 for record in output if record.get("status") == "scored")
    view_elapsed_values = [
        int(view.get("elapsed_ms"))
        for record in output
        for view in (record.get("views") or {}).values()
        if isinstance(view, dict) and isinstance(view.get("elapsed_ms"), int)
    ]
    run_summary = {
        "out": args.out,
        "records": len(output),
        "scored": scored_count,
        "backend": args.backend,
        "anchors": len(anchors),
        "workers": args.workers,
        "viewport_selection": args.viewport_selection,
        "quality_config": quality_config,
        "formal_report": bool(args.formal_report),
        "occlusion_overlap_check": OCCLUSION_OVERLAP_CHECK,
        "target_viewport_counts": {
            viewport: sum(1 for record in output if record.get("target_viewport") == viewport)
            for viewport in sorted(
                {str(record.get("target_viewport")) for record in output if record.get("target_viewport") is not None}
            )
        },
        "scored_viewport_counts": {
            viewport: sum(
                1
                for record in output
                for scored_viewport in record.get("scored_viewports", [])
                if scored_viewport == viewport
            )
            for viewport in sorted(
                {
                    str(scored_viewport)
                    for record in output
                    for scored_viewport in record.get("scored_viewports", [])
                }
            )
        },
        "started_at": run_started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(elapsed_seconds, 3),
        "avg_record_seconds": round(elapsed_seconds / len(output), 3) if output else None,
        "avg_scored_view_seconds": (
            round(sum(view_elapsed_values) / len(view_elapsed_values) / 1000, 3)
            if view_elapsed_values
            else None
        ),
    }
    summary_path = Path(args.out).with_suffix(".summary.json")
    summary_path.write_text(json.dumps(run_summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(
        json.dumps(
            run_summary | {"summary": str(summary_path)},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
