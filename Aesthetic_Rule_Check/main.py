from __future__ import annotations

import argparse
import json
from pathlib import Path

from aesthetic_rule_check import evaluate_card
from aesthetic_rule_check.models import EvaluationResult
from aesthetic_rule_check.reports import write_batch_index


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pure rule-based HarmonyOS card aesthetic checker.")
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--image", help="Single card screenshot path.")
    input_group.add_argument("--input-dir", help="Batch input directory containing card screenshots.")
    parser.add_argument("--dsl", help="DSL JSON/JSONL path. Missing DSL makes information score 0.")
    parser.add_argument("--dsl-dir", help="Batch DSL directory. Matches files by image stem, e.g. q1.png -> q1.jsonl.")
    parser.add_argument("--query", default="", help="Query text, recorded only; it does not affect scoring.")
    parser.add_argument("--out", default="reports/latest", help="Output directory for result.json and report.html.")
    parser.add_argument("--config", help="Config directory. Defaults to Aesthetic_Rule_Check/config.")
    parser.add_argument("--recursive", action="store_true", help="Batch mode: scan input directory recursively.")
    parser.add_argument("--print-json", action="store_true", help="Print result JSON to stdout.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.input_dir:
        results = run_batch(args)
        if args.print_json:
            print(json.dumps([result.to_dict() for result in results], ensure_ascii=False, indent=2))
        else:
            out_dir = Path(args.out).resolve()
            print(f"batch_total={len(results)}")
            print(f"index={out_dir / 'index.html'}")
            print(f"summary={out_dir / 'summary.json'}")
        return 0

    result = evaluate_card(
        image_path=Path(args.image),
        dsl_path=Path(args.dsl) if args.dsl else None,
        query=args.query,
        output_dir=Path(args.out),
        config_dir=Path(args.config) if args.config else None,
    )
    if args.print_json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"overall={result.overall:.2f} grade={result.grade} confidence={result.confidence:.2%}")
        print(f"report={Path(args.out).resolve() / 'report.html'}")
    return 0


def run_batch(args: argparse.Namespace) -> list[EvaluationResult]:
    input_dir = Path(args.input_dir)
    out_dir = Path(args.out).resolve()
    dsl_dir = Path(args.dsl_dir).resolve() if args.dsl_dir else None
    config_dir = Path(args.config).resolve() if args.config else None
    images = find_images(input_dir, recursive=bool(args.recursive))
    results: list[EvaluationResult] = []
    for image in images:
        item_out = out_dir / image.stem
        dsl = find_matching_dsl(image, dsl_dir)
        results.append(
            evaluate_card(
                image_path=image,
                dsl_path=dsl,
                query=args.query,
                output_dir=item_out,
                config_dir=config_dir,
            )
        )
    write_batch_index(results, out_dir)
    return results


def find_images(input_dir: Path, *, recursive: bool = False) -> list[Path]:
    pattern = "**/*" if recursive else "*"
    return sorted(
        path.resolve()
        for path in input_dir.glob(pattern)
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )


def find_matching_dsl(image_path: Path, dsl_dir: Path | None) -> Path | None:
    if dsl_dir is None:
        return None
    for suffix in (".jsonl", ".json"):
        candidate = dsl_dir / f"{image_path.stem}{suffix}"
        if candidate.exists():
            return candidate.resolve()
    return (dsl_dir / f"{image_path.stem}.jsonl").resolve()


if __name__ == "__main__":
    raise SystemExit(main())
