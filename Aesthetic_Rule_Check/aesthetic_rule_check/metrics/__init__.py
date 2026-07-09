from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

from .base import BaseMetric, MetricContext, create_metrics


def discover_metric_modules() -> None:
    package_dir = Path(__file__).resolve().parent
    for module in pkgutil.iter_modules([str(package_dir)]):
        if module.name == "base" or module.name.startswith("_"):
            continue
        importlib.import_module(f"{__name__}.{module.name}")


discover_metric_modules()

__all__ = ["BaseMetric", "MetricContext", "create_metrics"]
