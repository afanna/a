#!/usr/bin/env python3
"""Validate reader-facing aesthetic-v4 clean JSON files."""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

try:
    from aesthetic_contract import AXIS_IDS
except ModuleNotFoundError:
    from scripts.aesthetic_contract import AXIS_IDS


FORBIDDEN_KEYS = {
    "score_8",
    "axis_score_8",
    "axis_score_100",
    "final_score_8",
    "weighted_total_8",
    "weighted_contribution_8",
    "weighted_score_from_axis_scores",
    "weighted_score_from_axis_scores_100",
    "occlusion_weighted_loss_from_max",
    "weighted_contribution",
    "weighted_loss_from_max",
    "final_score_100",
    "score_100",
    "weighted_total_100",
    "score_100_rounded",
    "axis_breakdown",
}
FORBIDDEN_OCCLUSION_BEFORE_KEY = "score_" + "before_occlusion"

def walk_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            keys.append(str(key))
            keys.extend(walk_keys(child))
    elif isinstance(value, list):
        for item in value:
            keys.extend(walk_keys(item))
    return keys


def read_records(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(item for item in path.glob("*.json") if item.name != "index.json")
    if path.name == "index.json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        paths = []
        for row in payload.get("records") or []:
            if isinstance(row, dict) and row.get("json_path"):
                paths.append(Path(str(row["json_path"])))
        return paths
    return [path]


def validate(path: Path) -> list[str]:
    errors: list[str] = []
    payload = json.loads(path.read_text(encoding="utf-8"))
    keys = walk_keys(payload)
    forbidden = sorted(key for key in set(keys) if key in FORBIDDEN_KEYS or key.endswith("_8"))
    if forbidden:
        errors.append(f"forbidden keys: {', '.join(forbidden)}")
    if "score" in payload and isinstance(payload.get("score"), dict):
        errors.append("old top-level score object is not allowed")
    if "occlusion" in payload:
        errors.append("old top-level occlusion object is not allowed")
    if "views" in payload:
        errors.append("old top-level views array is not allowed")

    rubric = payload.get("aesthetic_rubric")
    if not isinstance(rubric, list):
        errors.append("missing aesthetic_rubric")
    elif [item.get("id") for item in rubric if isinstance(item, dict)] != AXIS_IDS:
        errors.append("aesthetic_rubric must contain the fixed 6 axes in order")
    else:
        for item in rubric:
            if not all(key in item for key in ("id", "display_id", "name", "weight", "weight_percent", "desc", "score_rule", "hard_fail")):
                errors.append(f"aesthetic_rubric item missing fields: {item.get('id')}")

    aesthetics = ((payload.get("extra_info_scores") or {}).get("aesthetics") or {})
    if not isinstance(aesthetics, dict):
        errors.append("missing extra_info_scores.aesthetics")
        aesthetics = {}
    if "score" not in aesthetics:
        errors.append("missing extra_info_scores.aesthetics.score")
    axis = aesthetics.get("axis_weighted_scores") if isinstance(aesthetics.get("axis_weighted_scores"), list) else []
    validate_axis_rows(axis, "extra_info_scores.aesthetics.axis_weighted_scores", errors)
    if axis and aesthetics.get("score") is not None:
        total = axis_total(axis)
        expected = Decimal(str(aesthetics.get("score")))
        if abs(total - expected) > Decimal("0.01"):
            errors.append(f"aesthetics score mismatch: {expected} vs axis sum {total}")

    adaptive = payload.get("adaptive_scores") if isinstance(payload.get("adaptive_scores"), dict) else {}
    if not adaptive:
        errors.append("missing adaptive_scores")
    views = adaptive.get("views") if isinstance(adaptive.get("views"), list) else []
    if not views:
        errors.append("missing adaptive_scores.views")
    for index, view in enumerate(views):
        if not isinstance(view, dict):
            errors.append(f"adaptive_scores.views[{index}] is not an object")
            continue
        if view.get("view") not in {"mobile", "web", "desktop", "image"}:
            errors.append(f"adaptive_scores.views[{index}].view is invalid")
        validate_axis_rows(
            view.get("axis_weighted_scores") if isinstance(view.get("axis_weighted_scores"), list) else [],
            f"adaptive_scores.views[{index}].axis_weighted_scores",
            errors,
        )
        occ = view.get("occlusion_overlap_check") if isinstance(view.get("occlusion_overlap_check"), dict) else {}
        validate_occlusion(occ, f"adaptive_scores.views[{index}].occlusion_overlap_check", errors)

    if "rationale" in payload and keys.count("rationale") != 1:
        errors.append(f"duplicated rationale keys: {keys.count('rationale')}")
    top_occ = payload.get("occlusion_overlap_check") if isinstance(payload.get("occlusion_overlap_check"), dict) else {}
    if not top_occ:
        errors.append("missing occlusion_overlap_check")
    for required in ("status", "detected", "failed_views", "passed_views"):
        if required not in top_occ:
            errors.append(f"missing occlusion_overlap_check.{required}")
    return errors


def axis_total(axis: list[dict[str, Any]]) -> Decimal:
    return sum(
        Decimal(str(item.get("weighted_contribution_100")))
        for item in axis
        if isinstance(item, dict) and item.get("weighted_contribution_100") is not None
    )


def validate_axis_rows(rows: list[Any], path: str, errors: list[str]) -> None:
    if len(rows) != 6:
        errors.append(f"{path} must contain exactly 6 axes")
        return
    ids = [row.get("id") for row in rows if isinstance(row, dict)]
    if ids != AXIS_IDS:
        errors.append(f"{path} must contain the fixed 6 axes in order")
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"{path}[{index}] is not an object")
            continue
        for required in ("id", "display_id", "name", "score", "weight", "weighted_contribution_100"):
            if required not in row:
                errors.append(f"missing {path}[{index}].{required}")
        if row.get("score") is not None and row.get("weight") is not None and row.get("weighted_contribution_100") is not None:
            expected = Decimal(str(row["score"])) * Decimal(str(row["weight"]))
            actual = Decimal(str(row["weighted_contribution_100"]))
            if abs(actual - expected) > Decimal("0.01"):
                errors.append(f"{path}[{index}] weighted_contribution_100 mismatch: {actual} vs {expected}")


def validate_occlusion(occ: dict[str, Any], path: str, errors: list[str]) -> None:
    if not occ:
        errors.append(f"missing {path}")
        return
    for required in ("status", "detected", "types", "affected_axes", "findings"):
        if required not in occ:
            errors.append(f"missing {path}.{required}")
    if occ.get("status") not in {"pass", "fail"}:
        errors.append(f"{path}.status must be pass or fail")
    if occ.get("status") == "fail" and "score_impact" not in occ:
        errors.append(f"missing {path}.score_impact for failed occlusion check")
    impact = occ.get("score_impact") if isinstance(occ.get("score_impact"), dict) else {}
    rows = impact.get("affected_axis_breakdown") if isinstance(impact.get("affected_axis_breakdown"), list) else []
    for index, row in enumerate(rows):
        if isinstance(row, dict) and FORBIDDEN_OCCLUSION_BEFORE_KEY in row:
            errors.append(
                f"{path}.score_impact.affected_axis_breakdown[{index}] must not include "
                f"{FORBIDDEN_OCCLUSION_BEFORE_KEY}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="Clean JSON file, index.json, or directory.")
    args = parser.parse_args()

    paths = read_records(Path(args.path))
    failures: dict[str, list[str]] = {}
    for path in paths:
        errors = validate(path)
        if errors:
            failures[str(path)] = errors

    summary = {"records": len(paths), "failed": len(failures), "failures": failures}
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
