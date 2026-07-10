#!/usr/bin/env python3
"""Export one clean review JSON per scored HTML/sample.

The raw score_images.py output is intentionally verbose and preserves nested
per-view payloads. This exporter creates a reader-facing JSON shape with no
duplicated rationale text while keeping score weights and occlusion evidence.
"""

from __future__ import annotations

import argparse
import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

try:
    from aesthetic_contract import (
        AXES_BY_ID,
        EXTERNAL_RUBRIC,
        axis_weighted_scores,
        display_viewport,
        round_3,
        score_to_100,
        weighted_total_100,
    )
except ModuleNotFoundError:
    from scripts.aesthetic_contract import (
        AXES_BY_ID,
        EXTERNAL_RUBRIC,
        axis_weighted_scores,
        display_viewport,
        round_3,
        score_to_100,
        weighted_total_100,
    )

try:
    from score_images import sanitize_public_rationale
except ModuleNotFoundError:
    from scripts.score_images import sanitize_public_rationale


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def qid_for(record: dict[str, Any]) -> str:
    candidates = [
        record.get("id"),
        record.get("sample_relpath"),
        record.get("input_path"),
        (record.get("sample_metadata") or {}).get("html_path"),
        (record.get("sample_metadata") or {}).get("source_id"),
    ]
    for value in candidates:
        if not value:
            continue
        match = re.search(r"q\d+", str(value), flags=re.I)
        if match:
            return match.group(0).lower()
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(record.get("id") or "sample")).strip("_")
    return safe or "sample"


def html_path_for(record: dict[str, Any]) -> str | None:
    metadata = record.get("sample_metadata") if isinstance(record.get("sample_metadata"), dict) else {}
    html_path = metadata.get("html_path")
    if html_path:
        return str(html_path)
    input_path = record.get("input_path")
    if isinstance(input_path, str) and input_path.lower().endswith((".html", ".htm")):
        return input_path
    return None


def view_image(view: dict[str, Any]) -> dict[str, Any]:
    image = view.get("image") if isinstance(view.get("image"), dict) else {}
    return {
        "path": image.get("path"),
        "width": image.get("width"),
        "height": image.get("height"),
        "sha256": image.get("sha256"),
    }


def quality_status(status: Any) -> str:
    return "success" if status == "scored" else str(status or "failed")


def aggregate_axis_weighted_scores(record: dict[str, Any]) -> list[dict[str, Any]]:
    aesthetics = (record.get("extra_info_scores") or {}).get("aesthetics") or {}
    axis_scores = aesthetics.get("axis_scores") if isinstance(aesthetics.get("axis_scores"), dict) else {}
    return axis_weighted_scores(axis_scores)


def clean_occlusion_impact(impact: Any) -> dict[str, Any] | None:
    if not isinstance(impact, dict):
        return None
    affected_axes = []
    for item in impact.get("affected_axes") if isinstance(impact.get("affected_axes"), list) else []:
        if not isinstance(item, dict):
            continue
        axis = item.get("axis")
        meta = AXES_BY_ID.get(str(axis), {})
        affected_axes.append(
            {
                "id": axis,
                "display_id": meta.get("display_id"),
                "name": meta.get("name") or axis,
                "score_after_occlusion": score_to_100(item.get("score")),
                "weight": item.get("weight"),
                "weighted_loss_100": score_to_100(item.get("weighted_loss_from_max")),
            }
        )
    if not affected_axes:
        return None
    total_loss = round_3(
        sum(
            Decimal(str(item["weighted_loss_100"]))
            for item in affected_axes
            if item.get("weighted_loss_100") is not None
        )
    )
    return {
        "affected_axis_breakdown": affected_axes,
        "total_weighted_loss_100": total_loss,
    }


def view_occlusion_payload(view: dict[str, Any]) -> dict[str, Any]:
    detected = bool(view.get("occlusion_overlap_detected"))
    payload: dict[str, Any] = {
        "status": "fail" if detected else "pass",
        "detected": detected,
        "types": view.get("occlusion_overlap_types") or [],
        "affected_axes": view.get("occlusion_overlap_affected_axes") or [],
        "findings": view.get("occlusion_findings") or [],
    }
    impact = clean_occlusion_impact(view.get("occlusion_score_impact"))
    if detected:
        payload["score_impact"] = impact or {
            "affected_axis_breakdown": [],
            "total_weighted_loss_100": 0,
        }
    return payload


def aggregate_strategy_label(formula: Any, views_payload: list[dict[str, Any]]) -> str:
    view_names = {str(view.get("view")) for view in views_payload}
    if formula == "min_of_available_views" and {"mobile", "web"}.issubset(view_names):
        return "mobile_web_min"
    if formula == "single_canonical_screenshot_score":
        return "single_view"
    if formula == "mean_of_available_views":
        return "mean_of_available_views"
    if formula == "not_scored":
        return "not_scored"
    return str(formula or "unknown")


def clean_views(record: dict[str, Any]) -> list[dict[str, Any]]:
    views = record.get("views") if isinstance(record.get("views"), dict) else {}
    cleaned: list[dict[str, Any]] = []
    for viewport, view in views.items():
        if not isinstance(view, dict):
            continue
        axis_rows = axis_weighted_scores(
            view.get("axis_scores") if isinstance(view.get("axis_scores"), dict) else {}
        )
        item = {
            "view": display_viewport(viewport),
            "score": weighted_total_100(axis_rows) or score_to_100(view.get("score")),
            "axis_weighted_scores": axis_rows,
            "designer_review": view.get("designer_review"),
            "occlusion_overlap_check": view_occlusion_payload(view),
            "image": view_image(view),
            "cache_hit": view.get("cache_hit"),
            "elapsed_ms": view.get("elapsed_ms"),
        }
        cleaned.append(item)
    return cleaned


def clean_record(record: dict[str, Any]) -> dict[str, Any]:
    aesthetics = (record.get("extra_info_scores") or {}).get("aesthetics") or {}
    sample_metadata = record.get("sample_metadata") if isinstance(record.get("sample_metadata"), dict) else {}
    axis_rows = aggregate_axis_weighted_scores(record)
    total_score = weighted_total_100(axis_rows)
    clean_views_payload = clean_views(record)
    aggregate_strategy = aggregate_strategy_label(record.get("aggregate_formula"), clean_views_payload)
    failed_views = [
        str(view.get("view"))
        for view in clean_views_payload
        if (view.get("occlusion_overlap_check") or {}).get("status") == "fail"
    ]
    passed_views = [
        str(view.get("view"))
        for view in clean_views_payload
        if (view.get("occlusion_overlap_check") or {}).get("status") == "pass"
    ]
    occlusion_detected = bool(failed_views)
    output = {
        "schema_version": 1,
        "id": record.get("id"),
        "qid": qid_for(record),
        "profile": record.get("profile"),
        "rubric_version": record.get("rubric_version"),
        "aesthetic_rubric": EXTERNAL_RUBRIC,
        "source": record.get("source"),
        "source_key": record.get("source_key"),
        "sample_relpath": record.get("sample_relpath"),
        "html_path": html_path_for(record),
        "sample_metadata": sample_metadata,
        "status": record.get("status"),
        "quality_config": record.get("quality_config") or {},
        "extra_info_scores": {
            "aesthetics": {
                "score": total_score,
                "status": quality_status(record.get("status")),
                "aggregate_strategy": aggregate_strategy,
                "aggregate_view": display_viewport(record.get("aggregate_view")),
                "axis_weighted_scores": axis_rows,
            }
        },
        "adaptive_scores": {
            "enabled": (record.get("quality_config") or {}).get("adaptive_viewports") in {"on", "auto"},
            "strategy": aggregate_strategy,
            "aggregate_view": display_viewport(record.get("aggregate_view")),
            "views": clean_views_payload,
        },
        "rationale": sanitize_public_rationale(record.get("rationale")),
        "designer_review": aesthetics.get("designer_review"),
        "occlusion_overlap_check": {
            "status": "fail" if occlusion_detected else "pass",
            "detected": occlusion_detected,
            "failed_views": failed_views,
            "passed_views": passed_views,
        },
        "links": {
            "html": html_path_for(record),
            "screenshots": [view["image"]["path"] for view in clean_views_payload if view["image"].get("path")],
        },
    }
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scores", nargs="+", required=True, help="Input scores JSONL files.")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--index", default=None)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    written: list[dict[str, Any]] = []
    seen: set[str] = set()
    for scores_path in [Path(path) for path in args.scores]:
        for record in read_jsonl(scores_path):
            clean = clean_record(record)
            key = clean.get("html_path") or clean.get("id") or clean.get("qid")
            if str(key) in seen:
                continue
            seen.add(str(key))
            qid = str(clean["qid"])
            out_path = out_dir / f"{qid}.json"
            write_json(out_path, clean)
            written.append(
                {
                    "id": clean.get("id"),
                    "qid": qid,
                    "html_path": clean.get("html_path"),
                    "json_path": str(out_path.resolve()),
                    "score": (clean.get("extra_info_scores") or {}).get("aesthetics", {}).get("score"),
                    "aggregate_view": (clean.get("extra_info_scores") or {}).get("aesthetics", {}).get("aggregate_view"),
                    "occlusion_overlap_check": {
                        "detected": clean["occlusion_overlap_check"].get("detected"),
                        "status": clean["occlusion_overlap_check"].get("status"),
                        "failed_views": clean["occlusion_overlap_check"].get("failed_views"),
                        "passed_views": clean["occlusion_overlap_check"].get("passed_views"),
                    },
                    "screenshots": clean["links"].get("screenshots") or [],
                }
            )

    index = {
        "schema_version": 1,
        "record_count": len(written),
        "records": sorted(written, key=lambda row: str(row["qid"])),
    }
    index_path = Path(args.index) if args.index else out_dir / "index.json"
    write_json(index_path, index)
    print(json.dumps({"out_dir": str(out_dir.resolve()), "index": str(index_path.resolve()), "records": len(written)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
