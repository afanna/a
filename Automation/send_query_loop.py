from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from automation.config import AutomationConfig, safe_path_name
from automation.hdc import HdcClient, HdcError
from automation.xiaoyi import XiaoyiClient


DEFAULT_INTERVAL_SECONDS = 300


@dataclass(frozen=True)
class QueryItem:
    qid: str
    query: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send Xiaoyi queries, wait five minutes, then screenshot.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--query", help="Single query text. It repeats until Ctrl+C unless --count is set.")
    source.add_argument("--queries", type=Path, help="Query file: JSONL with qid/query fields, or one query per line.")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SECONDS, help="Seconds to wait before screenshot.")
    parser.add_argument("--count", type=int, help="Maximum number of queries to send.")
    parser.add_argument("--repeat", action="store_true", help="Repeat --queries from the beginning after the file ends.")
    parser.add_argument("--qid-prefix", default="timed", help="Prefix for generated qid values.")
    parser.add_argument("--sn", help="Target HDC device SN.")
    parser.add_argument("--hdc", default="hdc", help="HDC executable.")
    parser.add_argument("--ready-timeout", type=float, default=60, help="Seconds to wait for Xiaoyi input to be ready.")
    parser.add_argument("--output-dir", type=Path, help="Screenshot output directory.")
    parser.add_argument("--remote-snapshot", default="/data/local/tmp/timed_query_snapshot.jpeg")
    parser.add_argument("--screenshot-min-bytes", type=int, default=1000)
    parser.add_argument("--screenshot-retries", type=int, default=3)
    parser.add_argument("--screenshot-write-wait", type=float, default=1)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.interval <= 0:
        raise SystemExit("--interval must be greater than 0")
    if args.count is not None and args.count <= 0:
        raise SystemExit("--count must be greater than 0")

    repo_root = Path(__file__).resolve().parents[1]
    items = load_query_items(args, repo_root)
    config = AutomationConfig(
        project_root=repo_root,
        hdc=args.hdc,
        sn=args.sn,
        ready_timeout=args.ready_timeout,
        remote_snapshot=args.remote_snapshot,
    )
    hdc = HdcClient(executable=config.hdc, sn=config.sn)
    validate_device(config, hdc)
    xiaoyi = XiaoyiClient(config, hdc)
    output_dir = args.output_dir or (config.output_dir / "timed_query")

    sent = 0
    try:
        while args.count is None or sent < args.count:
            item = items[sent % len(items)]
            if args.queries and sent >= len(items) and not args.repeat:
                break

            sent += 1
            qid = make_qid(item.qid or args.qid_prefix, sent)
            qid = safe_path_name(qid)
            print_status("send_start", sent, qid)
            xiaoyi.wait_ready()
            xiaoyi.send_query(item.query)
            print_status("sent", sent, qid)

            time.sleep(args.interval)

            screenshot = output_dir / f"{qid}.jpeg"
            hdc.snapshot_display(
                screenshot,
                config.remote_snapshot,
                min_bytes=args.screenshot_min_bytes,
                retries=args.screenshot_retries,
                write_wait=args.screenshot_write_wait,
            )
            print_status("screenshot", sent, qid, str(screenshot))
    except KeyboardInterrupt:
        print("Interrupted by user.")
        return 130
    except HdcError as exc:
        raise SystemExit(str(exc)) from exc

    return 0


def load_query_items(args: argparse.Namespace, repo_root: Path) -> list[QueryItem]:
    if args.query:
        return [QueryItem(qid=args.qid_prefix, query=args.query)]

    path = args.queries
    if path is None:
        raise SystemExit("--query or --queries is required")
    if not path.is_absolute():
        path = repo_root / path
    if not path.exists():
        raise SystemExit(f"Query file not found: {path}")

    items: list[QueryItem] = []
    with open(path, "r", encoding="utf-8") as f:
        for line_no, raw_line in enumerate(f, 1):
            line = raw_line.strip()
            if not line:
                continue
            item = parse_query_line(line, line_no)
            items.append(item)
    if not items:
        raise SystemExit(f"No queries found: {path}")
    return items


def parse_query_line(line: str, line_no: int) -> QueryItem:
    if line.startswith("{"):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid JSON at queries line {line_no}: {exc}") from exc
        if not isinstance(obj, dict):
            raise SystemExit(f"queries line {line_no} must be a JSON object")
        query = obj.get("query")
        if not isinstance(query, str) or not query.strip():
            raise SystemExit(f"queries line {line_no} missing non-empty query")
        qid = obj.get("qid")
        return QueryItem(qid=str(qid or f"q{line_no}"), query=query)
    return QueryItem(qid=f"q{line_no}", query=line)


def validate_device(config: AutomationConfig, hdc: HdcClient) -> None:
    devices = HdcClient.list_targets(config.hdc)
    if config.sn:
        if config.sn not in devices:
            raise SystemExit(f"HDC device not found: {config.sn}. Available devices: {', '.join(devices) or '[Empty]'}")
        return
    if not devices:
        raise SystemExit("No HDC devices found. Connect a device or pass --sn after it is online.")
    if len(devices) > 1:
        raise SystemExit(f"Multiple HDC devices found. Pass --sn with one of: {', '.join(devices)}")
    hdc.sn = devices[0]


def make_qid(prefix: str, run_index: int) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{timestamp}_{run_index:04d}"


def print_status(stage: str, run_index: int, qid: str, detail: str = "") -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    suffix = f" {detail}" if detail else ""
    print(f"[{now}] run={run_index} qid={qid} stage={stage}{suffix}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
