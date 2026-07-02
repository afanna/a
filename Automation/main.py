from __future__ import annotations

import argparse
from pathlib import Path

from automation.config import AutomationConfig
from automation.pipeline import AutomationPipeline
from automation.queries import QueryCase, load_queries


DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def add_common_arguments(parser: argparse.ArgumentParser, *, with_defaults: bool) -> None:
    default = None if with_defaults else argparse.SUPPRESS
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT if with_defaults else default)
    parser.add_argument("--hdc", default="hdc" if with_defaults else default)
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
    return parser


def make_config(args: argparse.Namespace) -> AutomationConfig:
    values = {
        "project_root": args.project_root,
        "hdc": args.hdc,
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


def print_result(qid: str, dsl_path: Path, screenshot_path: Path) -> None:
    print(f"{qid}: DSL={dsl_path} SCREENSHOT={screenshot_path}")


if __name__ == "__main__":
    raise SystemExit(main())

