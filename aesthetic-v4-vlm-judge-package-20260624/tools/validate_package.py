#!/usr/bin/env python3
"""Validate the aesthetic-v4 package layout and public naming."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PUBLIC_TOKENS = [
    ("old_person_name", "bo" + "bo"),
    ("local_mount_path", "/" + "Volumes" + "/" + "TU820"),
    ("local_home_path", "/" + "Users" + "/" + "ze" + "nan" + "chen"),
    ("old_handoff_path", "handoff" + "_packages"),
    ("old_acceptance_dir", "bench" + "mark" + "_claude47"),
    ("old_full_set_name", "full" + "72"),
    ("old_run_dir", "aesthetic" + "_v1"),
    ("removed_provider_name", "pa" + "cky"),
]
FORBIDDEN_PUBLIC_PATTERNS = [
    ("legacy_prompt_alias", re.compile(r"blind[-_]boundary")),
    ("legacy_prompt_version", re.compile(r"(?<![a-z0-9_-])v(?:28|29)(?![a-z0-9_-])")),
    ("old_bench_mark_token", re.compile("bench" + "mark")),
]
REQUIRED = [
    "README.md",
    "config/aesthetic-v4.env.example",
    "docs/AESTHETIC_V4_WORKFLOW.md",
    "input_html/sample_aesthetic_v4_dashboard.html",
    ".gitignore",
    "pipeline/run_aesthetic_v4.sh",
    "pipeline/package.json",
    "pipeline/scripts/aesthetic_contract.py",
    "pipeline/scripts/build_html_manifest.py",
    "pipeline/scripts/build_aesthetic_v4_report.py",
    "pipeline/scripts/build_manual_qc.py",
    "pipeline/scripts/codex_rubric_judge.py",
    "pipeline/scripts/export_clean_html_score_json.py",
    "pipeline/scripts/model_judge_adapter.py",
    "pipeline/scripts/pangu_rubric_judge.py",
    "pipeline/scripts/score_images.py",
    "pipeline/scripts/validate_clean_json.py",
    "pipeline/scripts/render_screenshots.mjs",
    "tools/build_handoff_zip.py",
]


def fail(message: str) -> int:
    print(f"FAIL: {message}", file=sys.stderr)
    return 1


def main() -> int:
    missing = [path for path in REQUIRED if not (ROOT / path).exists()]
    if missing:
        return fail("missing required files: " + ", ".join(missing))

    forbidden: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.name.startswith("._"):
            continue
        if path.suffix.lower() not in {".py", ".md", ".json", ".jsonl", ".html", ".sh", ".txt", ".csv"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        hits = [label for label, token in FORBIDDEN_PUBLIC_TOKENS if token in text]
        hits.extend(label for label, pattern in FORBIDDEN_PUBLIC_PATTERNS if pattern.search(text))
        if hits:
            forbidden.append(f"{path.relative_to(ROOT)} ({', '.join(hits)})")
    if forbidden:
        return fail("forbidden public token found in: " + ", ".join(forbidden))

    env_text = (ROOT / "config/aesthetic-v4.env.example").read_text(encoding="utf-8")
    if "PANGU_BASE_URL=http://43.139.21.243:4000" not in env_text:
        return fail("env example must use the Pangu gateway base URL")
    if "PANGU_JUDGE_MODEL=claude-opus-4-7-thinking" not in env_text:
        return fail("env example must default Pangu to Claude 4.7")
    if "PANGU_JUDGE_OUTPUT_MODE=full" not in env_text:
        return fail("env example must default to full output mode")
    expected_env_defaults = [
        "AESTHETIC_V4_SCREENSHOT_MODE=fullpage",
        "AESTHETIC_V4_MANIFEST_VIEWPORT=all",
        "AESTHETIC_V4_VIEWPORT=all",
        "AESTHETIC_V4_ADAPTIVE_VIEWPORTS=on",
        "AESTHETIC_V4_SCORE_BREAKDOWN=on",
        "AESTHETIC_V4_DESIGNER_REVIEW=on",
        "AESTHETIC_V4_OUTPUT_JSON=on",
        "AESTHETIC_V4_OUTPUT_HTML=off",
        "AESTHETIC_V4_OCCLUSION_OVERLAP_CHECK=always_on",
    ]
    missing_env_defaults = [line for line in expected_env_defaults if line not in env_text]
    if missing_env_defaults:
        return fail("env example missing default-on controls: " + ", ".join(missing_env_defaults))
    for line in env_text.splitlines():
        if line.startswith("PANGU_API_KEY=") and not line.strip().endswith("="):
            return fail("env example must not contain a real API key")

    scripts_dir = ROOT / "pipeline/scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    prompt_path = scripts_dir / "codex_rubric_judge.py"
    spec = importlib.util.spec_from_file_location("codex_rubric_judge", prompt_path)
    if spec is None or spec.loader is None:
        return fail("cannot load prompt module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    prompt = module.build_prompt(
        {
            "rubric_version": "aesthetic_static_v1",
            "image": {"sample_id": "validate", "viewport": "desktop", "width": 1440, "height": 900},
        },
        "aesthetic-v4",
    )
    prompt_lower = prompt.lower()
    prompt_forbidden_hits = [
        label for label, token in FORBIDDEN_PUBLIC_TOKENS if token in prompt_lower
    ]
    prompt_forbidden_hits.extend(
        label for label, pattern in FORBIDDEN_PUBLIC_PATTERNS if pattern.search(prompt_lower)
    )
    if "aesthetic-v4" not in prompt or prompt_forbidden_hits:
        return fail("prompt public naming validation failed")

    print("OK: aesthetic-v4 package validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
