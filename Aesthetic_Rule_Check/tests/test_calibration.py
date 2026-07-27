"""P0-3 偏差标定单测：calibrated_overall 计算、向后兼容与等级映射。"""
from __future__ import annotations

from pathlib import Path

import pytest

from aesthetic_rule_check.config import Config
from aesthetic_rule_check.fusion import calibrate_overall

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_DIR = PACKAGE_ROOT / "config"


def test_calibration_from_default_config() -> None:
    config = Config(DEFAULT_CONFIG_DIR)
    params = config.calibration()
    assert params is not None
    assert params["method"] == "linear"
    assert params["a"] == pytest.approx(0.830716)
    assert params["b"] == pytest.approx(11.831671)


def test_calibrate_overall_clamps_and_rounds_to_half() -> None:
    config = Config(DEFAULT_CONFIG_DIR)
    # 0.830716 * 62.5 + 11.831671 = 63.751... -> 64.0（取整到 0.5）
    assert calibrate_overall(62.5, config) == 64.0
    # 负分 clamp 到 0
    assert calibrate_overall(-50.0, config) == 0.0
    # 超 100 clamp 到 100
    assert calibrate_overall(200.0, config) == 100.0


def test_calibrate_overall_backward_compatible_without_section(tmp_path: Path) -> None:
    (tmp_path / "score.yaml").write_text(
        "dimensions:\n  geometry:\n    weight: 1\n    label: g\ngrades:\n  D: 0\n",
        encoding="utf-8",
    )
    (tmp_path / "metrics.yaml").write_text("{}\n", encoding="utf-8")
    config = Config(tmp_path)
    assert config.calibration() is None
    assert calibrate_overall(62.5, config) == 62.5
