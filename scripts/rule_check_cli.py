"""单命令纯规则美学检测：输入 DSL 与图片，按文件名自动匹配并评分。

不需要连设备。对每张图片按文件名（不含扩展名）在 DSL 目录中找同名 .jsonl，
匹配到的按 DSL+图片评分，未匹配到的按纯图片评分并给出提示。
最后自动聚合生成 model_scores.jsonl 与 model_report.html 画廊报告。

用法（从仓库根目录运行）：

    # 目录对目录：dsl/*.jsonl 与 output/card/*.png 按文件名自动配对
    python scripts/rule_check_cli.py --dsl dsl --images output/card

    # 单个文件对单个文件
    python scripts/rule_check_cli.py --dsl dsl/q1.jsonl --images output/card/q1.png

    # 附带 query 文本（提高 information 维度准确性），按 id=文件名自动查找
    python scripts/rule_check_cli.py --dsl dsl --images output/card --queries queries_100.jsonl

    # 隔离输出目录：报告写到 output/{namespace}/reports/
    python scripts/rule_check_cli.py --dsl dsl --images output/card --namespace rerun1

注意：本机 Python 需安装 cv2 / rapidocr / yaml 等依赖（见 requirements.txt）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Automation"))

from automation.config import AutomationConfig  # noqa: E402
from automation.rule_check import evaluate_card_image  # noqa: E402
from automation.rule_summary import build_rule_summary  # noqa: E402

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def collect_images(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise SystemExit(f"图片路径不存在: {path}")
    images = [p for p in sorted(path.iterdir()) if p.suffix.lower() in IMAGE_SUFFIXES and p.is_file()]
    if not images:
        raise SystemExit(f"图片目录中没有图片文件: {path}")
    return images


def collect_dsl_map(path: Path) -> dict[str, Path]:
    if path.is_file():
        return {path.stem: path}
    if not path.is_dir():
        raise SystemExit(f"DSL 路径不存在: {path}")
    return {p.stem: p for p in sorted(path.glob("*.jsonl")) if p.is_file()}


def load_query_map(path: Path | None) -> dict[str, str]:
    if not path:
        return {}
    if not path.is_file():
        raise SystemExit(f"queries 文件不存在: {path}")
    mapping: dict[str, str] = {}
    with path.open(encoding="utf-8-sig") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            if "id" in item and "query" in item:
                mapping[str(item["id"])] = str(item["query"])
    return mapping


def main() -> int:
    parser = argparse.ArgumentParser(description="DSL+图片 自动匹配纯规则美学检测")
    parser.add_argument("--dsl", type=Path, required=True, help="DSL 文件或目录（目录时按文件名自动匹配）")
    parser.add_argument("--images", type=Path, required=True, help="图片文件或目录（png/jpg/jpeg/webp）")
    parser.add_argument("--queries", type=Path, default=None, help="可选 queries JSONL，按 id=文件名自动带入 query 文本")
    parser.add_argument("--query", type=str, default="", help="可选 query 文本，应用于全部样本（--queries 优先）")
    parser.add_argument("--namespace", type=str, default=None, help="可选隔离名，报告写到 output/{namespace}/reports/")
    args = parser.parse_args()

    images = collect_images(args.images)
    dsl_map = collect_dsl_map(args.dsl)
    query_map = load_query_map(args.queries)

    config = AutomationConfig(project_root=ROOT, enable_rule_check=True, artifact_namespace=args.namespace)

    done: list[str] = []
    for image_path in images:
        qid = image_path.stem
        dsl_path = dsl_map.get(qid)
        if dsl_path is None and args.dsl.is_file() and len(images) == 1:
            dsl_path = next(iter(dsl_map.values()))
        query = query_map.get(qid, args.query)
        try:
            report_dir = evaluate_card_image(config, qid=qid, query=query, dsl_path=dsl_path, image_path=image_path)
        except Exception as exc:
            print(f"[fail] {qid}: {exc}")
            continue
        result_path = report_dir / "result.json"
        score_text = ""
        if result_path.exists():
            data = json.loads(result_path.read_text(encoding="utf-8"))
            score_text = f" overall={data.get('overall', 0):.1f} grade={data.get('grade', '-')}"
        dsl_note = "" if dsl_path else " (无匹配DSL，纯图片评分)"
        print(f"[ok] {qid}{score_text}{dsl_note}")
        done.append(qid)

    outputs = build_rule_summary(config, done)
    print(f"\n完成 {len(done)}/{len(images)} 张")
    if outputs:
        print(f"分数文件: {outputs[0]}")
        print(f"画廊报告: {outputs[1]}")
    return 0 if done else 1


if __name__ == "__main__":
    raise SystemExit(main())
