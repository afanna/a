"""Batch scoring script for card images.

Walks ``batch_test/``, finds all ``.png`` files, matches them with
``_query.txt`` and ``_dsl.json``, scores each card, and writes a
``summary.csv`` with all results.

Usage:
    python scripts/batch_score.py
    python scripts/batch_score.py --input batch_test/ --output reports/batch/
"""

from __future__ import annotations

import csv
import logging
import sys
from pathlib import Path

# Ensure project root is on path
_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

from card_scorer.configs.loader import Config
from card_scorer.engine.context import build_context
from card_scorer.engine.scorer import score
from card_scorer.reports.json_report import save as save_json
from card_scorer.reports.html_report import save as save_html

logger = logging.getLogger(__name__)


def _find_fixtures(fixtures_dir: Path) -> list[dict[str, str]]:
    """Scan fixtures directory for card groups.

    A group consists of:
        <name>.png          (required)
        <name>_query.txt    (optional)
        <name>_dsl.json     (optional)

    Returns list of dicts with keys: name, image, query, dsl.
    """
    groups: dict[str, dict[str, str]] = {}

    for png in sorted(fixtures_dir.glob("*.png")):
        name = png.stem
        groups[name] = {"name": name, "image": str(png), "query": "", "dsl": ""}

    for txt in sorted(fixtures_dir.glob("*_query.txt")):
        # Strip _query suffix to get base name
        base = txt.stem
        if base.endswith("_query"):
            base = base[:-6]
        if base in groups:
            groups[base]["query"] = str(txt)

    for dsl in sorted(fixtures_dir.glob("*_dsl.json")):
        base = dsl.stem
        if base.endswith("_dsl"):
            base = base[:-4]
        if base in groups:
            groups[base]["dsl"] = str(dsl)

    return list(groups.values())


def _read_query(query_path: str) -> str:
    """Read query text from file, or return path if it's not a file."""
    if not query_path:
        return ""
    p = Path(query_path)
    if p.exists() and p.suffix in (".txt", ".text"):
        return p.read_text(encoding="utf-8").strip()
    return query_path


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Batch score card images")
    parser.add_argument(
        "--input", default="batch_test",
        help="Path to input directory containing images (default: batch_test)",
    )
    parser.add_argument(
        "--output", default="reports/batch",
        help="Output directory for reports (default: reports/batch)",
    )
    args = parser.parse_args()

    input_dir = _project_root / args.input
    output_dir = _project_root / args.output

    if not input_dir.exists():
        print(f"Input directory not found: {input_dir}")
        print("Create it and add .png files to get started.")
        sys.exit(1)

    groups = _find_fixtures(input_dir)
    if not groups:
        print(f"No .png files found in {input_dir}")
        sys.exit(1)

    print(f"Found {len(groups)} card(s) in {input_dir}")
    print()

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "summary.csv"

    rows: list[dict] = []

    for i, g in enumerate(groups, 1):
        name = g["name"]
        image = g["image"]
        query = _read_query(g["query"])
        dsl = g["dsl"]

        print(f"[{i}/{len(groups)}] {name} ... ", end="", flush=True)

        try:
            ctx, _ = build_context(
                image_path=image,
                query=query,
                dsl_path=dsl,
            )
            report = score(ctx)

            # Save individual reports (JSON + HTML)
            card_out = output_dir / name
            card_out.mkdir(parents=True, exist_ok=True)
            save_json(report, str(card_out / "report.json"))
            save_html(report, str(card_out / "report.html"), image_path=image)

            # Collect summary row
            fatal_count = sum(
                1 for r in report.deduction_details
                if r.severity.value == "fatal"
            )
            major_count = sum(
                1 for r in report.deduction_details
                if r.severity.value == "major"
            )
            minor_count = sum(
                1 for r in report.deduction_details
                if r.severity.value == "minor"
            )

            rows.append({
                "name": name,
                "score": report.total_score,
                "status": report.status,
                "fatal": fatal_count,
                "major": major_count,
                "minor": minor_count,
                "total_issues": len(report.deduction_details),
                "top_issue": report.deduction_details[0].rule_id if report.deduction_details else "",
                "top_issue_desc": report.deduction_details[0].explanation if report.deduction_details else "",
            })

            print(f"{report.total_score} ({report.status})")

        except Exception as e:
            print(f"ERROR: {e}")
            rows.append({
                "name": name,
                "score": "ERROR",
                "status": "ERROR",
                "fatal": 0,
                "major": 0,
                "minor": 0,
                "total_issues": 0,
                "top_issue": str(e),
                "top_issue_desc": "",
            })

    # Write CSV
    fieldnames = [
        "name", "score", "status", "fatal", "major", "minor",
        "total_issues", "top_issue", "top_issue_desc",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # Summary
    passed = sum(1 for r in rows if r["status"] == "PASS")
    failed = sum(1 for r in rows if r["status"] == "FAIL")
    errors = sum(1 for r in rows if r["status"] == "ERROR")

    print()
    print(f"Done. {passed} PASS, {failed} FAIL, {errors} ERROR")
    print(f"Summary: {csv_path}")
    print(f"Reports: {output_dir}")


if __name__ == "__main__":
    main()
