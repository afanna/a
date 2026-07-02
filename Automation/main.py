from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from automation.config import AutomationConfig
from automation.hdc import HdcClient
from automation.pipeline import AutomationPipeline
from automation.queries import QueryCase, load_queries


DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def add_common_arguments(parser: argparse.ArgumentParser, *, with_defaults: bool) -> None:
    default = None if with_defaults else argparse.SUPPRESS
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT if with_defaults else default)
    parser.add_argument("--hdc", default="hdc" if with_defaults else default)
    parser.add_argument("--sn", default=None if with_defaults else default)
    parser.add_argument("--extract-delay", type=float, default=30 if with_defaults else default)
    parser.add_argument("--reply-timeout", type=float, default=120 if with_defaults else default)
    parser.add_argument("--post-query-wait", type=float, default=30 if with_defaults else default)
    parser.add_argument("--query-attempt-timeout", type=float, default=90 if with_defaults else default)
    parser.add_argument("--query-max-attempts", type=int, default=3 if with_defaults else default)
    parser.add_argument("--build-timeout", type=float, default=300 if with_defaults else default)
    parser.add_argument("--render-wait", type=float, default=5 if with_defaults else default)
    parser.add_argument("--deveco-sdk-home", type=Path, default=default)
    parser.add_argument("--java-home", type=Path, default=default)
    parser.add_argument("--bundle-name", default="yyx.test.test" if with_defaults else default)
    parser.add_argument("--ability-name", default="EntryAbility" if with_defaults else default)
    parser.add_argument("--module-name", default="entry" if with_defaults else default)
    parser.add_argument("--screenshot-min-bytes", type=int, default=1000 if with_defaults else default)
    parser.add_argument("--screenshot-retries", type=int, default=3 if with_defaults else default)
    parser.add_argument("--screenshot-write-wait", type=float, default=1 if with_defaults else default)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Xiaoyi DSL render automation")
    add_common_arguments(parser, with_defaults=True)
    subparsers = parser.add_subparsers(dest="command", required=True)

    one = subparsers.add_parser("one", help="Send one query, extract DSL, render, and screenshot")
    add_common_arguments(one, with_defaults=False)
    one.add_argument("--qid", default="manual")
    one.add_argument("--query", required=True)

    from_file = subparsers.add_parser("one-from-file", help="Run one query from queries.jsonl by id")
    add_common_arguments(from_file, with_defaults=False)
    from_file.add_argument("--qid", required=True)
    from_file.add_argument("--queries", type=Path)

    batch = subparsers.add_parser("batch", help="Collect all DSLs first, then render all screenshots")
    add_common_arguments(batch, with_defaults=False)
    batch.add_argument("--queries", type=Path)

    parallel = subparsers.add_parser("parallel", help="Run the full query batch on multiple devices")
    add_common_arguments(parallel, with_defaults=False)
    parallel.add_argument("--queries", type=Path)
    parallel.add_argument("--devices", default="auto", help="Use 'auto' or a comma-separated SN list")
    parallel.add_argument("--max-workers", type=int)
    return parser


def make_config(args: argparse.Namespace, *, sn: str | None = None) -> AutomationConfig:
    values = {
        "project_root": args.project_root,
        "hdc": args.hdc,
        "sn": sn if sn is not None else args.sn,
        "extract_delay": args.extract_delay,
        "reply_timeout": args.reply_timeout,
        "post_query_wait": args.post_query_wait,
        "query_attempt_timeout": args.query_attempt_timeout,
        "query_max_attempts": args.query_max_attempts,
        "build_timeout": args.build_timeout,
        "render_wait": args.render_wait,
        "bundle_name": args.bundle_name,
        "ability_name": args.ability_name,
        "module_name": args.module_name,
        "screenshot_min_bytes": args.screenshot_min_bytes,
        "screenshot_retries": args.screenshot_retries,
        "screenshot_write_wait": args.screenshot_write_wait,
    }
    if args.deveco_sdk_home is not None:
        values["deveco_sdk_home"] = args.deveco_sdk_home
    if args.java_home is not None:
        values["java_home"] = args.java_home
    return AutomationConfig(**values)


def main() -> int:
    args = build_parser().parse_args()

    if args.command == "parallel":
        return run_parallel(args)

    config = make_config(args)
    pipeline = AutomationPipeline(config)

    if args.command == "one":
        result = pipeline.run_one(QueryCase(qid=args.qid, query=args.query))
        print_result(result.qid, result.dsl_path, result.screenshot_path)
        return 0

    if args.command == "one-from-file":
        queries = load_queries(args.queries or config.queries_path)
        matches = [case for case in queries if case.qid == args.qid]
        if not matches:
            raise SystemExit(f"Query id not found: {args.qid}")
        result = pipeline.run_one(matches[0])
        print_result(result.qid, result.dsl_path, result.screenshot_path)
        return 0

    if args.command == "batch":
        for result in pipeline.run_batch(args.queries):
            print_result(result.qid, result.dsl_path, result.screenshot_path)
        return 0

    raise AssertionError(args.command)


def run_parallel(args: argparse.Namespace) -> int:
    devices = resolve_devices(args.devices, args.hdc)
    max_workers = args.max_workers or len(devices)
    if max_workers < 1:
        raise SystemExit("--max-workers must be greater than 0")

    print(f"Parallel devices: {', '.join(devices)}")
    failed = False
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_by_sn = {executor.submit(run_batch_for_device, args, sn): sn for sn in devices}
        for future in as_completed(future_by_sn):
            sn = future_by_sn[future]
            try:
                results = future.result()
            except Exception as exc:
                failed = True
                print(f"[{sn}] FAILED: {exc}")
                continue
            for result in results:
                print_result(result.qid, result.dsl_path, result.screenshot_path, sn=sn)

    return 1 if failed else 0


def run_batch_for_device(args: argparse.Namespace, sn: str):
    config = make_config(args, sn=sn)
    pipeline = AutomationPipeline(config)
    return pipeline.run_batch(args.queries)


def resolve_devices(raw_devices: str, hdc: str) -> list[str]:
    if raw_devices.strip().lower() == "auto":
        devices = HdcClient.list_targets(hdc)
    else:
        devices = [part.strip() for part in raw_devices.split(",") if part.strip()]

    unique_devices: list[str] = []
    for device in devices:
        if device not in unique_devices:
            unique_devices.append(device)
    if not unique_devices:
        raise SystemExit("No HDC devices found. Connect devices or pass --devices SN1,SN2.")
    return unique_devices


def print_result(qid: str, dsl_path: Path, screenshot_path: Path, *, sn: str | None = None) -> None:
    prefix = f"[{sn}] " if sn else ""
    print(f"{prefix}{qid}: DSL={dsl_path} SCREENSHOT={screenshot_path}")


if __name__ == "__main__":
    raise SystemExit(main())

