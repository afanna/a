from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_DIR = PACKAGE_ROOT / "config"


class Config:
    def __init__(self, config_dir: Path | None = None) -> None:
        self.config_dir = config_dir or DEFAULT_CONFIG_DIR
        self.score = self._load_yaml("score.yaml")
        self.metrics = self._load_yaml("metrics.yaml")

    def _load_yaml(self, name: str) -> dict[str, Any]:
        path = self.config_dir / name
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            raise ValueError(f"Config file must contain an object: {path}")
        return data

    def dimension_weight(self, dimension: str) -> float:
        return float(self.score["dimensions"][dimension]["weight"])

    def dimension_label(self, dimension: str) -> str:
        return str(self.score["dimensions"][dimension].get("label") or dimension)

    def dimension_names(self) -> list[str]:
        dimensions = self.score.get("dimensions", {})
        return list(dimensions) if isinstance(dimensions, dict) else []

    def metric_config(self, dimension: str, metric: str) -> dict[str, Any]:
        section = self.metrics.get(dimension, {})
        metrics = section.get("metrics", {}) if isinstance(section, dict) else {}
        config = metrics.get(metric, {}) if isinstance(metrics, dict) else {}
        return config if isinstance(config, dict) else {}

    def section(self, name: str) -> dict[str, Any]:
        section = self.metrics.get(name, {})
        return section if isinstance(section, dict) else {}

    def grade_for(self, score: float) -> str:
        grades = self.score.get("grades", {})
        ordered = sorted(((str(k), float(v)) for k, v in grades.items()), key=lambda item: item[1], reverse=True)
        for grade, minimum in ordered:
            if score >= minimum:
                return grade
        return "D"
