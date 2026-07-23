from __future__ import annotations

from pathlib import Path

from .config import Config
from .dsl import load_dsl_info
from .fusion import build_result, run_metrics
from .metrics import MetricContext
from .models import EvaluationResult
from .reports import write_outputs
from .vision import build_vision_context


def evaluate_card(
    image_path: str | Path,
    dsl_path: str | Path | None = None,
    query: str = "",
    output_dir: str | Path | None = None,
    config_dir: str | Path | None = None,
) -> EvaluationResult:
    image = Path(image_path).resolve()
    dsl = Path(dsl_path).resolve() if dsl_path else None
    config = Config(Path(config_dir).resolve() if config_dir else None)
    dsl_info = load_dsl_info(dsl)
    vision = build_vision_context(image)
    context = MetricContext(query=query, dsl=dsl_info, vision=vision, config=config)
    metrics = run_metrics(context)
    result = build_result(context, metrics, config)
    if output_dir is not None:
        write_outputs(result, Path(output_dir).resolve())
    return result
