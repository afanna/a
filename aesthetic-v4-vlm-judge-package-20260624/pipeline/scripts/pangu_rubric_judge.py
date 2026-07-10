#!/usr/bin/env python3
"""Pangu/Mix API visual judge backend for score_images.py."""

from __future__ import annotations

from model_judge_adapter import ApiJudgeConfig, run_api_judge


DEFAULT_BASE_URL = "http://43.139.21.243:4000"
DEFAULT_MODEL = "claude-opus-4-7-thinking"

CONFIG = ApiJudgeConfig(
    judge_name="pangu_rubric_judge",
    description=__doc__ or "",
    default_base_url=DEFAULT_BASE_URL,
    default_model=DEFAULT_MODEL,
    base_url_env="PANGU_BASE_URL",
    model_env="PANGU_JUDGE_MODEL",
    prompt_version_env="PANGU_JUDGE_PROMPT_VERSION",
    output_mode_env="PANGU_JUDGE_OUTPUT_MODE",
    api_key_env="PANGU_API_KEY",
    timeout_env="PANGU_JUDGE_TIMEOUT",
    max_retries_env="PANGU_JUDGE_MAX_RETRIES",
    token_arg="--max-tokens",
    token_param="max_tokens",
    token_env="PANGU_JUDGE_MAX_TOKENS",
    default_token_budget=1200,
    temperature_env="PANGU_JUDGE_TEMPERATURE",
    default_temperature=0.0,
    parse_max_retries_env="PANGU_JUDGE_PARSE_MAX_RETRIES",
    default_parse_max_retries=2,
)


def main() -> int:
    return run_api_judge(CONFIG)


if __name__ == "__main__":
    raise SystemExit(main())
