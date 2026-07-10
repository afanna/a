#!/usr/bin/env python3
"""Shared OpenAI-compatible VLM judge adapter helpers."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import sys
import time
import argparse
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from aesthetic_contract import AXIS_IDS, AXIS_WEIGHTS, BOUNDARY_BUCKET_SCORES, clamp_score
from codex_rubric_judge import (
    OCCLUSION_OVERLAP_CHECK,
    apply_occlusion_axis_penalties,
    axis_scores_are_uniform,
    build_prompt,
    build_occlusion_score_impact,
    calibrate_axis_scores_to_total,
    fallback_axis_scores_for_uniform_bucket,
    normalize_designer_review,
    normalize_occlusion_findings,
    weighted_axis_score,
)


RETRIABLE_STATUS_CODES = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class ApiJudgeConfig:
    judge_name: str
    description: str
    default_base_url: str
    default_model: str
    base_url_env: str
    model_env: str
    prompt_version_env: str
    output_mode_env: str
    api_key_env: str
    timeout_env: str
    max_retries_env: str
    token_arg: str
    token_param: str
    token_env: str
    default_token_budget: int = 1200
    temperature_env: str | None = None
    default_temperature: float | None = None
    reasoning_effort_env: str | None = None
    image_detail_env: str | None = None
    default_image_detail: str = "high"
    parse_max_retries_env: str | None = None
    default_parse_max_retries: int = 0


def redact_secret(text: str) -> str:
    return re.sub(r"sk-[A-Za-z0-9_-]{8,}", "sk-REDACTED", text)


def data_url_for_image(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        return json.loads(stripped[start : end + 1])
    raise ValueError(f"model output did not contain JSON: {text[:500]}")


def content_text(message_content: Any) -> str:
    if isinstance(message_content, str):
        return message_content
    if isinstance(message_content, list):
        parts: list[str] = []
        for item in message_content:
            if isinstance(item, dict):
                value = item.get("text") or item.get("content")
                if isinstance(value, str):
                    parts.append(value)
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return str(message_content)


def score_only_prompt() -> str:
    return (
        "你是严格的 UI 静态截图审美评分 judge。只看图片本身。"
        "只输出 JSON object，格式必须是 {\"score\": number}。"
        "score 是 0 到 8 的审美分，一位小数即可。"
        "不要输出理由、轴分、遮挡分析、建议或任何其他字段。"
    )


def endpoint_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, str(default)))


def env_float(name: str, default: float) -> float:
    return float(os.environ.get(name, str(default)))


def env_optional_float(name: str | None, default: float | None) -> float | None:
    if name and os.environ.get(name) not in {None, ""}:
        return float(str(os.environ[name]))
    return default


def parse_api_args(config: ApiJudgeConfig) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=config.description)
    parser.add_argument("--base-url", default=os.environ.get(config.base_url_env, config.default_base_url))
    parser.add_argument("--model", default=os.environ.get(config.model_env, config.default_model))
    parser.add_argument("--prompt-version", default=os.environ.get(config.prompt_version_env, "aesthetic-v4"))
    parser.add_argument(
        "--output-mode",
        choices=["full", "score-only"],
        default=os.environ.get(config.output_mode_env, "full"),
    )
    parser.add_argument("--api-key-env", default=config.api_key_env)
    parser.add_argument(
        config.token_arg,
        dest="token_budget",
        type=int,
        default=env_int(config.token_env, config.default_token_budget),
    )
    parser.add_argument("--timeout", type=float, default=env_float(config.timeout_env, 240.0))
    parser.add_argument("--max-retries", type=int, default=env_int(config.max_retries_env, 4))
    parser.add_argument("--retry-base-sleep", type=float, default=1.0)
    parser.add_argument("--retry-max-sleep", type=float, default=16.0)
    parser.add_argument(
        "--parse-max-retries",
        type=int,
        default=env_int(config.parse_max_retries_env, config.default_parse_max_retries)
        if config.parse_max_retries_env
        else config.default_parse_max_retries,
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=env_optional_float(config.temperature_env, config.default_temperature),
    )
    if config.reasoning_effort_env:
        parser.add_argument("--reasoning-effort", default=os.environ.get(config.reasoning_effort_env))
    else:
        parser.set_defaults(reasoning_effort=None)
    if config.image_detail_env:
        parser.add_argument(
            "--image-detail",
            choices=["low", "high", "auto"],
            default=os.environ.get(config.image_detail_env, config.default_image_detail),
        )
    else:
        parser.set_defaults(image_detail=config.default_image_detail)
    return parser.parse_args()


def build_api_payload(
    *,
    config: ApiJudgeConfig,
    request: dict[str, Any],
    prompt_version: str,
    model: str,
    output_mode: str,
    token_budget: int,
    include_response_format: bool,
    image_detail: str,
    temperature: float | None,
    reasoning_effort: str | None,
    parse_retry: bool,
) -> dict[str, Any]:
    image_path = Path(request["image"]["path"]).resolve()
    if output_mode == "score-only":
        prompt = score_only_prompt()
    else:
        prompt = build_prompt(request, prompt_version)
    if parse_retry:
        prompt += (
            "\n\n上一次输出不是合法 JSON。现在必须只输出一个可被 json.loads 解析的 JSON object。"
            "不要使用 Markdown，不要在字符串外写解释；字符串内部的双引号必须转义。"
        )
    payload: dict[str, Any] = {
        "model": model,
        config.token_param: token_budget,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": data_url_for_image(image_path),
                            "detail": image_detail,
                        },
                    },
                ],
            }
        ],
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort
    if include_response_format:
        payload["response_format"] = {"type": "json_object"}
    return payload


def call_api_model(
    *,
    config: ApiJudgeConfig,
    args: argparse.Namespace,
    request: dict[str, Any],
    token: str,
    parse_retry: bool,
) -> tuple[dict[str, Any], int]:
    url = endpoint_url(args.base_url)
    with httpx.Client() as client:
        return call_chat_completions_with_retries(
            client=client,
            url=url,
            token=token,
            timeout=args.timeout,
            max_retries=args.max_retries,
            retry_base_sleep=args.retry_base_sleep,
            retry_max_sleep=args.retry_max_sleep,
            build_payload=lambda include_response_format: build_api_payload(
                config=config,
                request=request,
                prompt_version=args.prompt_version,
                model=args.model,
                output_mode=args.output_mode,
                token_budget=args.token_budget,
                include_response_format=include_response_format,
                image_detail=args.image_detail,
                temperature=args.temperature,
                reasoning_effort=args.reasoning_effort,
                parse_retry=parse_retry,
            ),
        )


def run_api_judge(config: ApiJudgeConfig) -> int:
    args = parse_api_args(config)
    token = os.environ.get(args.api_key_env)
    if not token:
        raise SystemExit(f"{args.api_key_env} is not set")

    request = json.loads(sys.stdin.read())
    started = time.perf_counter()
    try:
        payload: dict[str, Any] | None = None
        retry_count = 0
        last_parse_error: Exception | None = None
        for parse_attempt in range(args.parse_max_retries + 1):
            raw, api_retry_count = call_api_model(
                config=config,
                args=args,
                request=request,
                token=token,
                parse_retry=parse_attempt > 0,
            )
            retry_count += api_retry_count
            choices = raw.get("choices") or []
            if not choices:
                raise RuntimeError(f"API response has no choices: {json.dumps(raw, ensure_ascii=False)[:1000]}")
            message = choices[0].get("message") or {}
            text = content_text(message.get("content"))
            try:
                payload = extract_json_object(text)
                break
            except Exception as exc:
                last_parse_error = exc
                retry_count += 1
                if parse_attempt >= args.parse_max_retries:
                    raise
                time.sleep(min(args.retry_max_sleep, args.retry_base_sleep * (2**parse_attempt)))
        if payload is None:
            raise RuntimeError(str(last_parse_error or "model output did not contain JSON"))
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        normalized = normalize_model_payload(
            payload,
            judge_name=config.judge_name,
            model=args.model,
            prompt_version=args.prompt_version,
            output_mode=args.output_mode,
            elapsed_ms=elapsed_ms,
            retry_count=retry_count,
        )
        normalized["backend_meta"]["endpoint_url"] = endpoint_url(args.base_url)
        normalized["backend_meta"]["image_detail"] = args.image_detail
    except Exception as exc:
        raise SystemExit(redact_secret(str(exc))[:10000])

    sys.stdout.write(json.dumps(normalized, ensure_ascii=False, sort_keys=True))
    return 0


def fixed_boundary_bucket(payload: dict[str, Any], rationale: str) -> tuple[str | None, float | None]:
    bucket = str(payload.get("bucket") or "").strip()
    if bucket not in BOUNDARY_BUCKET_SCORES:
        match = re.search(r"\[(?:0|10|20|30|40|50|60|70),(?:10|20|30|40|50|60|70|80)\)|\[80,100\]", rationale)
        bucket = match.group(0) if match else ""
    if bucket in BOUNDARY_BUCKET_SCORES:
        return bucket, BOUNDARY_BUCKET_SCORES[bucket]
    return None, None


def normalize_model_payload(
    payload: dict[str, Any],
    *,
    judge_name: str,
    model: str,
    prompt_version: str,
    output_mode: str,
    elapsed_ms: int,
    retry_count: int,
) -> dict[str, Any]:
    if "score" not in payload:
        raise ValueError("judge response must include score")

    if output_mode == "score-only":
        score = clamp_score(payload["score"])
        axis_scores = {key: score for key in AXIS_IDS}
        impact = build_occlusion_score_impact(axis_scores, [])
        return {
            "score": score,
            "axis_scores": axis_scores,
            "rationale": "score_only",
            "occlusion_overlap_check": OCCLUSION_OVERLAP_CHECK,
            "occlusion_findings": [],
            "occlusion_score_impact": impact,
            "designer_review": None,
            "backend_meta": {
                "judge": judge_name,
                "model": model,
                "prompt_version": prompt_version,
                "output_mode": output_mode,
                "elapsed_ms": elapsed_ms,
                "retry_count": retry_count,
                "scored_at": datetime.now(timezone.utc).isoformat(),
                "rubric_weights": AXIS_WEIGHTS,
            },
        }

    raw_axis = payload.get("axis_scores")
    if not isinstance(raw_axis, dict):
        raw_axis = {}
    score = clamp_score(payload["score"])
    rationale = str(payload.get("rationale") or "").strip()[:1000]
    boundary_bucket = None
    boundary_score = None
    axis_scores_fallback = None
    if prompt_version in {"aesthetic-v4", "aesthetic_v4"}:
        boundary_bucket, boundary_score = fixed_boundary_bucket(payload, rationale)
        if boundary_score is not None:
            score = boundary_score
    zero_defect = rationale.startswith("ZERO_DEFECT:")
    axis_scores = {key: clamp_score(raw_axis.get(key, score)) for key in AXIS_IDS}
    if boundary_score is not None:
        if axis_scores_are_uniform(axis_scores):
            axis_scores = fallback_axis_scores_for_uniform_bucket(boundary_score, rationale)
            axis_scores_fallback = "uniform_model_axis_scores"
        axis_scores = calibrate_axis_scores_to_total(axis_scores, boundary_score)

    findings = normalize_occlusion_findings(
        payload,
        rationale=rationale,
        axis_scores=axis_scores,
        score=score,
    )
    if findings:
        axis_scores = apply_occlusion_axis_penalties(axis_scores, findings)
    weighted = weighted_axis_score(axis_scores)
    if boundary_score is not None:
        score = weighted
    elif zero_defect or abs(weighted - score) > 0.25:
        score = weighted
    impact = build_occlusion_score_impact(axis_scores, findings)

    backend_meta = dict(payload.get("backend_meta") or {})
    backend_meta.update(
        {
            "judge": judge_name,
            "model": model,
            "prompt_version": prompt_version,
            "output_mode": output_mode,
            "elapsed_ms": elapsed_ms,
            "retry_count": retry_count,
            "scored_at": datetime.now(timezone.utc).isoformat(),
            "rubric_weights": AXIS_WEIGHTS,
        }
    )
    if boundary_bucket:
        backend_meta["bucket"] = boundary_bucket
    if axis_scores_fallback:
        backend_meta["axis_scores_fallback"] = axis_scores_fallback
    return {
        "score": score,
        "axis_scores": axis_scores,
        "rationale": rationale,
        "occlusion_overlap_check": OCCLUSION_OVERLAP_CHECK,
        "occlusion_findings": findings,
        "occlusion_score_impact": impact,
        "designer_review": normalize_designer_review(payload.get("designer_review")),
        "backend_meta": backend_meta,
    }


def should_retry_without_response_format(status_code: int, body: str) -> bool:
    lowered = body.lower()
    if status_code not in {400, 404, 422}:
        return False
    return "response_format" in lowered or "json_object" in lowered or "unsupported" in lowered


def post_chat_completions(
    *,
    client: httpx.Client,
    url: str,
    token: str,
    payload: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    response = client.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=timeout,
    )
    if response.status_code >= 400:
        raise httpx.HTTPStatusError(
            redact_secret(response.text[:4000]),
            request=response.request,
            response=response,
        )
    return response.json()


def call_chat_completions_with_retries(
    *,
    client: httpx.Client,
    url: str,
    token: str,
    timeout: float,
    max_retries: int,
    retry_base_sleep: float,
    retry_max_sleep: float,
    build_payload: Callable[[bool], dict[str, Any]],
) -> tuple[dict[str, Any], int]:
    include_response_format = True
    retry_count = 0
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        payload = build_payload(include_response_format)
        try:
            return post_chat_completions(
                client=client,
                url=url,
                token=token,
                payload=payload,
                timeout=timeout,
            ), retry_count
        except httpx.HTTPStatusError as exc:
            last_error = exc
            status_code = exc.response.status_code
            body = exc.response.text[:4000]
            if include_response_format and should_retry_without_response_format(status_code, body):
                include_response_format = False
                retry_count += 1
                continue
            if status_code not in RETRIABLE_STATUS_CODES or attempt >= max_retries:
                break
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = exc
            if attempt >= max_retries:
                break

        retry_count += 1
        time.sleep(min(retry_max_sleep, retry_base_sleep * (2**attempt)))

    raise RuntimeError(redact_secret(str(last_error or "unknown API error")))
