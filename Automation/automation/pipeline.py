from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from .arkts import ArkTsRunner
from .card_crop import CardCropper, load_card_crop_config
from .config import AutomationConfig
from .hdc import HdcClient
from .logger import get_logger
from .queries import QueryCase, load_queries
from .xiaoyi import QueryResult, XiaoyiClient


@dataclass(frozen=True)
class RenderResult:
    qid: str
    dsl_path: Path
    screenshot_path: Path
    card_path: Path | None = None


class AutomationPipeline:
    def __init__(self, config: AutomationConfig, aesthetics_config=None):
        self.config = config
        self._log = get_logger("pipeline", sn=config.safe_sn or "", log_dir=config.output_dir, debug=config.debug)
        hdc_log = get_logger("hdc", sn=config.safe_sn or "", log_dir=config.output_dir, debug=config.debug)
        self.hdc = HdcClient(config.hdc, sn=config.sn, logger=hdc_log)
        self.xiaoyi = XiaoyiClient(config, self.hdc)
        self.arkts = ArkTsRunner(config, self.hdc)
        self.aesthetics_config = aesthetics_config
        self.card_cropper = self._create_card_cropper() if self._should_crop_cards() else None

        self.aesthetics_judge = None
        if self.aesthetics_config and self.aesthetics_config.enable:
            import sys

            sys.path.insert(0, str(self.config.project_root))
            from visual_aesthetics.judge import VisualAestheticsJudge

            self.aesthetics_judge = VisualAestheticsJudge(self.aesthetics_config)

    def run_one(self, case: QueryCase) -> RenderResult:
        """Run one query through DSL extraction, render, screenshot, and optional scoring."""
        query_result = self.xiaoyi.collect_dsl_for_query(case.qid, case.query)
        screenshot = self.arkts.render(case.qid, query_result.dsl_path)
        card_path = self._crop_card(case.qid, screenshot)
        result = RenderResult(case.qid, query_result.dsl_path, screenshot, card_path)

        if self.aesthetics_judge and card_path:
            self.aesthetics_judge.judge_image(card_path, case.qid, self.config.safe_sn or "")
        elif self.aesthetics_judge:
            self._log.error("Aesthetics skipped because card crop failed: qid=%s screenshot=%s", case.qid, screenshot)

        return result

    def run_batch(self, queries_path: Path | None = None) -> list[RenderResult]:
        """Run all queries, then render screenshots and optionally build an aesthetics report."""
        t0 = time.monotonic()
        cases = load_queries(queries_path or self.config.queries_path)

        dsl_fail = 0
        query_results: list[QueryResult] = []
        for case in cases:
            try:
                query_results.append(self.xiaoyi.collect_dsl_for_query(case.qid, case.query))
            except TimeoutError as exc:
                dsl_fail += 1
                self._log.error("DSL failed: qid=%s error=%s", case.qid, exc)
                continue

        render_fail = 0
        render_results: list[RenderResult] = []
        for result in query_results:
            try:
                screenshot = self.arkts.render(result.qid, result.dsl_path)
            except Exception as exc:
                render_fail += 1
                self._log.error("Render failed: qid=%s dsl=%s error=%s", result.qid, result.dsl_path, exc)
                continue
            card_path = self._crop_card(result.qid, screenshot)
            render_results.append(RenderResult(result.qid, result.dsl_path, screenshot, card_path))

        if self.aesthetics_judge and render_results:
            card_paths = [result.card_path for result in render_results if result.card_path is not None]
            if not card_paths:
                self._log.error("Aesthetics skipped because no cropped card images were generated")
            else:
                self.aesthetics_judge.judge_images(
                    card_paths,
                    sn=self.config.safe_sn or "",
                    output_jsonl_path=self.config.scores_jsonl_path,
                )
                self.aesthetics_judge.build_report(
                    self.config.scores_jsonl_path,
                    self.config.report_html_path,
                    image_dir=self.config.output_dir,
                )

        total_elapsed = time.monotonic() - t0
        self._log.info("=" * 60)
        self._log.info(
            "BATCH SUMMARY: total=%d dsl_ok=%d dsl_fail=%d render_ok=%d render_fail=%d card_ok=%d card_fail=%d total_time=%.1fs",
            len(cases),
            len(query_results),
            dsl_fail,
            len(render_results),
            render_fail,
            sum(1 for result in render_results if result.card_path is not None),
            sum(1 for result in render_results if result.card_path is None),
            total_elapsed,
        )
        self._log.info("=" * 60)
        return render_results

    def _should_crop_cards(self) -> bool:
        return self.config.enable_card_crop or bool(self.aesthetics_config and self.aesthetics_config.enable)

    def _create_card_cropper(self) -> CardCropper:
        config_path = self.config.card_crop_config or self.config.default_card_crop_config_path
        return CardCropper(load_card_crop_config(config_path))

    def _crop_card(self, qid: str, screenshot: Path) -> Path | None:
        if not self.card_cropper:
            return None

        try:
            result = self.card_cropper.crop(
                screenshot,
                self.config.output_dir,
                output_path=self.config.card_screenshot_path_for(qid),
                debug=self.config.card_crop_debug,
                debug_dir=self.config.card_crop_debug_dir,
            )
        except Exception as exc:
            self._log.error("Card crop failed: qid=%s screenshot=%s error=%s", qid, screenshot, exc)
            return None

        self._log.info(
            "Card crop done: qid=%s type=%s box=%s output=%s",
            qid,
            result.card_type,
            result.box,
            result.card_path,
        )
        return result.card_path
