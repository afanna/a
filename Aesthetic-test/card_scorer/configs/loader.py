"""Configuration loader.

Reads YAML config files from the configs/ directory.
All thresholds and weights are loaded here -- never hardcoded in rules.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

# Default config directory: <project_root>/configs/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_DIR = _PROJECT_ROOT / "configs"


def _load_yaml(filename: str, config_dir: Path | None = None) -> dict[str, Any]:
    """Load a YAML file and return its contents as a dict."""
    directory = config_dir or _CONFIG_DIR
    filepath = directory / filename
    if not filepath.exists():
        raise FileNotFoundError(f"Config file not found: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class Config:
    """Singleton-style config holder.

    Usage::

        cfg = Config.load()
        margin = cfg.threshold("layout", "edge_margin_min_px")
        max_ded = cfg.weight("information", "max_deduction")
    """

    _instance: Config | None = None

    def __init__(
        self,
        weights: dict[str, Any],
        thresholds: dict[str, Any],
    ) -> None:
        self._weights = weights
        self._thresholds = thresholds

    # ---- Factory ----------------------------------------------------------

    @classmethod
    def load(cls, config_dir: Path | None = None) -> Config:
        """Load (or return cached) configuration."""
        if cls._instance is not None:
            return cls._instance
        weights = _load_yaml("weights.yaml", config_dir)
        thresholds = _load_yaml("thresholds.yaml", config_dir)
        cls._instance = cls(weights=weights, thresholds=thresholds)
        return cls._instance

    @classmethod
    def reload(cls, config_dir: Path | None = None) -> Config:
        """Force-reload configuration (useful for tests)."""
        cls._instance = None
        return cls.load(config_dir)

    # ---- Accessors --------------------------------------------------------

    @property
    def base_score(self) -> float:
        return float(self._weights.get("base_score", 100))

    @property
    def fail_cap(self) -> float:
        return float(self._weights.get("fail_cap", 60))

    def weight(self, dimension: str, key: str) -> Any:
        """Get a weight parameter for a dimension.

        Example: ``cfg.weight("information", "max_deduction")``
        """
        dims = self._weights.get("dimensions", {})
        dim = dims.get(dimension, {})
        if key not in dim:
            raise KeyError(
                f"Weight key '{key}' not found in dimension '{dimension}'"
            )
        return dim[key]

    def threshold(self, section: str, key: str) -> Any:
        """Get a threshold parameter.

        Example: ``cfg.threshold("layout", "edge_margin_min_px")``
        """
        sec = self._thresholds.get(section, {})
        if key not in sec:
            raise KeyError(
                f"Threshold key '{key}' not found in section '{section}'"
            )
        return sec[key]

    def threshold_section(self, section: str) -> dict[str, Any]:
        """Get an entire threshold section as a dict."""
        return dict(self._thresholds.get(section, {}))

    def weights_raw(self) -> dict[str, Any]:
        """Raw weights dict (for report metadata)."""
        return dict(self._weights)

    def thresholds_raw(self) -> dict[str, Any]:
        """Raw thresholds dict (for report metadata)."""
        return dict(self._thresholds)
