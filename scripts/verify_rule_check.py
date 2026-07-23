"""离线验证：不连设备，直接对现有 output/*.png 样本跑纯规则评分并聚合。

用法：
    python scripts/verify_rule_check.py [qid ...]

不带参数时跑全部 6 对样本（dsl/{qid}.jsonl + output/{qid}.png）。
注意：本机需使用带 cv2/rapidocr/yaml 的 Python 解释器。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Automation"))

from automation.config import AutomationConfig  # noqa: E402
from automation.rule_check import evaluate_card_image  # noqa: E402
from automation.rule_summary import build_rule_summary  # noqa: E402

DEFAULT_QIDS = [
    "codex_experiment_01_weather_clean",
    "codex_experiment_02_meeting_clean",
    "codex_experiment_03_battery_ring",
    "codex_experiment_04_dense_info",
    "codex_experiment_05_overlap_defect",
    "Case-600-30-pet-feeder-020.card.dsl",
]


def main() -> int:
    qids = sys.argv[1:] or DEFAULT_QIDS
    config = AutomationConfig(project_root=ROOT, enable_rule_check=True)

    done: list[str] = []
    for qid in qids:
        image_path = ROOT / "output" / f"{qid}.png"
        dsl_path = config.dsl_path_for(qid)
        if not image_path.exists():
            print(f"[skip] 缺少卡片图: {image_path}")
            continue
        report_dir = evaluate_card_image(
            config,
            qid=qid,
            query="",  # 现有样本与 queries.jsonl 的 qid 不对应，离线验证用空 query
            dsl_path=dsl_path if dsl_path.exists() else None,
            image_path=image_path,
        )
        print(f"[ok] {qid} -> {report_dir}")
        done.append(qid)

    outputs = build_rule_summary(config, done)
    print(f"[summary] {outputs}")
    return 0 if done else 1


if __name__ == "__main__":
    raise SystemExit(main())
