from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from ..config import Config
from ..models import DslInfo, MetricResult, VisionContext


@dataclass(frozen=True)
class MetricContext:
    query: str
    dsl: DslInfo
    vision: VisionContext
    config: Config


class BaseMetric(ABC):
    name: ClassVar[str]
    dimension: ClassVar[str]

    @abstractmethod
    def evaluate(self, context: MetricContext) -> MetricResult:
        raise NotImplementedError

    def cfg(self, context: MetricContext) -> dict:
        return context.config.metric_config(self.dimension, self.name)


_REGISTRY: dict[tuple[str, str], type[BaseMetric]] = {}


def register_metric(cls: type[BaseMetric]) -> type[BaseMetric]:
    key = (str(cls.dimension), str(cls.name))
    if not key[0] or not key[1]:
        raise ValueError("Metric classes must define non-empty dimension and name.")
    _REGISTRY[key] = cls
    return cls


def create_metrics() -> list[BaseMetric]:
    return [cls() for cls in _REGISTRY.values()]


def registered_metric_keys() -> list[tuple[str, str]]:
    return list(_REGISTRY)
