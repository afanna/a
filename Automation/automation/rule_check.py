"""纯规则美学评分接线。

内置的 Aesthetic_Rule_Check 规则包位于项目根的 Aesthetic_Rule_Check/ 目录，
这里负责把它加入 sys.path 并调用 evaluate_card。
调用方负责捕获异常，评分失败不能中断自动化主流程。
"""

from __future__ import annotations

import sys
from pathlib import Path

from .config import AutomationConfig


def resolve_rule_check_config_dir(config: AutomationConfig) -> Path:
    """解析规则评分配置目录：优先用户配置，缺省回退内置 Aesthetic_Rule_Check/config。"""
    config_dir = config.rule_check_config_dir or config.default_rule_check_config_dir
    if not config_dir.is_absolute():
        config_dir = config.project_root / config_dir
    return config_dir.resolve()


def _ensure_rule_package_importable(config: AutomationConfig) -> None:
    """把内置规则包所在目录加入 sys.path（整个进程只需一次）。"""
    package_root = (config.project_root / "Aesthetic_Rule_Check").resolve()
    entry = str(package_root)
    if entry not in sys.path:
        sys.path.insert(0, entry)


def evaluate_card_image(
    config: AutomationConfig,
    *,
    qid: str,
    query: str,
    dsl_path: Path | None,
    image_path: Path,
) -> Path:
    """对单张卡片图执行纯规则评分，返回单样本报告目录 output/reports/{qid}。"""
    _ensure_rule_package_importable(config)
    from aesthetic_rule_check import evaluate_card

    output_dir = config.rule_report_dir_for(qid)
    dsl = Path(dsl_path) if dsl_path else None
    evaluate_card(
        image_path=image_path,
        dsl_path=dsl if dsl and dsl.exists() else None,
        query=query or "",
        output_dir=output_dir,
        config_dir=resolve_rule_check_config_dir(config),
    )
    return output_dir
