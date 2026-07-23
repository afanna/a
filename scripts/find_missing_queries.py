"""找出尚未执行成功的 query，生成用于重跑的 queries 文件。

判定依据：queries 文件中的每条 id，对应 dsl/{safe_path_name(id)}.jsonl 是否存在。
可选 --check-content 进一步校验 DSL 内容完整（防止文件存在但提取不完整）。

用法（从仓库根目录运行）：

    python scripts/find_missing_queries.py --queries queries_100.jsonl
    python scripts/find_missing_queries.py --queries queries_100.jsonl --check-content
    python scripts/find_missing_queries.py --queries queries_100.jsonl --output queries_retry.jsonl

生成的输出文件与输入格式一致，可直接用于：

    python Automation/main.py batch --queries queries_retry.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "Automation"))

from automation.config import safe_path_name  # noqa: E402
from automation.dsl import is_complete_dsl  # noqa: E402


def load_queries(path: Path) -> list[dict]:
    queries: list[dict] = []
    with path.open(encoding="utf-8-sig") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{lineno} 不是合法 JSON：{exc}")
            if "id" not in item or "query" not in item:
                raise SystemExit(f"{path}:{lineno} 缺少 id 或 query 字段：{line[:80]}")
            queries.append(item)
    return queries


def dsl_is_complete(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return False
    records: list[dict] = []
    try:
        value = json.loads(text)
        if isinstance(value, list):
            records = value
        elif isinstance(value, dict):
            records = [value]
    except json.JSONDecodeError:
        # 兼容逐行 JSONL 格式
        for line in text.splitlines():
            line = line.strip().rstrip(",")
            if not line or line in {"[", "]"}:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                return False
    return bool(records) and is_complete_dsl(records)


def main() -> int:
    parser = argparse.ArgumentParser(description="检测未执行的 query 并生成重跑文件")
    parser.add_argument("--queries", type=Path, required=True, help="原始 queries JSONL 文件")
    parser.add_argument("--dsl-dir", type=Path, default=Path("dsl"), help="DSL 产物目录，默认 dsl/")
    parser.add_argument("--output", type=Path, default=None, help="输出文件，默认 <queries文件名>_retry.jsonl")
    parser.add_argument("--check-content", action="store_true", help="额外校验 DSL 内容完整性（更严格）")
    args = parser.parse_args()

    queries = load_queries(args.queries)
    output = args.output or args.queries.with_name(f"{args.queries.stem}_retry.jsonl")

    missing: list[dict] = []
    done = 0
    for item in queries:
        qid = str(item["id"])
        dsl_path = args.dsl_dir / f"{safe_path_name(qid)}.jsonl"
        ok = dsl_path.is_file() and dsl_path.stat().st_size > 0
        if ok and args.check_content:
            ok = dsl_is_complete(dsl_path)
        if ok:
            done += 1
        else:
            missing.append(item)

    with output.open("w", encoding="utf-8", newline="\n") as fh:
        for item in missing:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"queries 总数 : {len(queries)}")
    print(f"已完成       : {done}")
    print(f"待重跑       : {len(missing)}")
    print(f"输出文件     : {output}")
    if missing:
        print("待重跑 id    :")
        for item in missing:
            print(f"  - {item['id']}")
        print(f"\n重跑命令：python Automation/main.py batch --queries {output}")
    else:
        print("全部 query 已完成，无需重跑。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
