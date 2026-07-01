from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .arkts import ArkTsRunner
from .config import AutomationConfig
from .hdc import HdcClient
from .queries import QueryCase, load_queries
from .xiaoyi import QueryResult, XiaoyiClient


@dataclass(frozen=True)
class RenderResult:
    qid: str
    dsl_path: Path
    screenshot_path: Path


class AutomationPipeline:
    def __init__(self, config: AutomationConfig):
        self.config = config
        self.hdc = HdcClient(config.hdc)
        self.xiaoyi = XiaoyiClient(config, self.hdc)
        self.arkts = ArkTsRunner(config, self.hdc)

    def run_one(self, case: QueryCase) -> RenderResult:
        query_result = self.xiaoyi.collect_dsl_for_query(case.qid, case.query)
        screenshot = self.arkts.render(case.qid, query_result.dsl_path)
        return RenderResult(case.qid, query_result.dsl_path, screenshot)

    def run_batch(self, queries_path: Path | None = None) -> list[RenderResult]:
        cases = load_queries(queries_path or self.config.queries_path)
        query_results: list[QueryResult] = []
        for case in cases:
            try:
                query_results.append(self.xiaoyi.collect_dsl_for_query(case.qid, case.query))
            except TimeoutError:
                continue

        render_results: list[RenderResult] = []
        for result in query_results:
            screenshot = self.arkts.render(result.qid, result.dsl_path)
            render_results.append(RenderResult(result.qid, result.dsl_path, screenshot))
        return render_results

