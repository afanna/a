from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

from .arkts import ArkTsRunner
from .card_crop import CardCropper, load_card_crop_config
from .config import AutomationConfig
from .hdc import HdcClient, HdcError
from .logger import get_logger
from .queries import QueryCase, load_queries
from .xiaoyi import QueryResult, XiaoyiClient


@dataclass(frozen=True)
class RenderResult:
    qid: str
    dsl_path: Path
    screenshot_path: Path
    card_path: Path | None = None
    rule_result: Any | None = None


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
        rule_result = self._score_rule_card(case.qid, query_result.dsl_path, card_path, query=case.query)
        result = RenderResult(case.qid, query_result.dsl_path, screenshot, card_path, rule_result)

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
        query_results = self.collect_dsls(queries_path, log_summary=False)
        dsl_fail = len(cases) - len(query_results)

        query_by_qid = {case.qid: case.query for case in cases}
        render_results = self.render_dsl_files(
            [result.dsl_path for result in query_results],
            log_summary=False,
            query_by_qid=query_by_qid,
        )
        render_fail = len(query_results) - len(render_results)

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
            "BATCH SUMMARY: total=%d dsl_ok=%d dsl_fail=%d render_ok=%d render_fail=%d card_ok=%d card_fail=%d rule_ok=%d rule_fail=%d total_time=%.1fs",
            len(cases),
            len(query_results),
            dsl_fail,
            len(render_results),
            render_fail,
            sum(1 for result in render_results if result.card_path is not None),
            sum(1 for result in render_results if result.card_path is None),
            sum(1 for result in render_results if result.rule_result is not None),
            sum(1 for result in render_results if result.rule_result is None),
            total_elapsed,
        )
        self._log.info("=" * 60)
        return render_results

    def collect_dsls(self, queries_path: Path | None = None, *, log_summary: bool = True) -> list[QueryResult]:
        """Send all queries and save DSL files without rendering."""
        t0 = time.monotonic()
        cases = load_queries(queries_path or self.config.queries_path)
        query_results: list[QueryResult] = []
        failed = 0
        for case in cases:
            try:
                query_results.append(self.xiaoyi.collect_dsl_for_query(case.qid, case.query))
            except (TimeoutError, HdcError) as exc:
                failed += 1
                self._log.error("DSL failed: qid=%s error=%s", case.qid, exc)
                continue

        if log_summary:
            self._log.info(
                "DSL SUMMARY: total=%d ok=%d failed=%d total_time=%.1fs",
                len(cases),
                len(query_results),
                failed,
                time.monotonic() - t0,
            )
        return query_results

    def render_dsl_dir(self, dsl_dir: Path | None = None) -> list[RenderResult]:
        """Render every DSL file under a directory, then screenshot and optionally crop."""
        directory = dsl_dir or self.config.dsl_dir
        dsl_files = sorted(directory.glob("*.jsonl"))
        if not dsl_files:
            self._log.error("No DSL files found: %s", directory)
            return []
        return self.render_dsl_files(dsl_files)

    def render_dsl_files(
        self,
        dsl_files: list[Path],
        *,
        log_summary: bool = True,
        query_by_qid: dict[str, str] | None = None,
    ) -> list[RenderResult]:
        t0 = time.monotonic()
        render_fail = 0
        render_results: list[RenderResult] = []
        query_by_qid = query_by_qid or {}
        for dsl_path in dsl_files:
            qid = qid_from_dsl_path(dsl_path, self.config.safe_sn)
            try:
                screenshot = self.arkts.render(qid, dsl_path)
            except Exception as exc:
                render_fail += 1
                self._log.error("Render failed: qid=%s dsl=%s error=%s", qid, dsl_path, exc)
                continue
            card_path = self._crop_card(qid, screenshot)
            rule_result = self._score_rule_card(qid, dsl_path, card_path, query=query_by_qid.get(qid, ""))
            render_results.append(RenderResult(qid, dsl_path, screenshot, card_path, rule_result))

        self._write_rule_batch_report(render_results)

        if log_summary:
            self._log.info(
                "RENDER SUMMARY: total=%d ok=%d failed=%d card_ok=%d card_fail=%d rule_ok=%d rule_fail=%d total_time=%.1fs",
                len(dsl_files),
                len(render_results),
                render_fail,
                sum(1 for result in render_results if result.card_path is not None),
                sum(1 for result in render_results if result.card_path is None),
                sum(1 for result in render_results if result.rule_result is not None),
                sum(1 for result in render_results if result.rule_result is None),
                time.monotonic() - t0,
            )
        return render_results

    def _should_crop_cards(self) -> bool:
        return (
            self.config.enable_card_crop
            or self.config.enable_rule_check
            or bool(self.aesthetics_config and self.aesthetics_config.enable)
        )

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

    def _score_rule_card(self, qid: str, dsl_path: Path, card_path: Path | None, *, query: str) -> Any | None:
        if not self.config.enable_rule_check:
            return None
        if card_path is None:
            self._log.error("Rule scoring skipped because card crop failed: qid=%s dsl=%s", qid, dsl_path)
            return None

        try:
            evaluate_card = self._load_rule_evaluator()
            result = evaluate_card(
                image_path=card_path,
                dsl_path=dsl_path,
                query=query,
                output_dir=self.config.rule_report_dir_for(qid),
                config_dir=self.config.rule_check_config_dir or self.config.default_rule_check_config_dir,
            )
        except Exception as exc:
            self._log.error("Rule scoring failed: qid=%s card=%s dsl=%s error=%s", qid, card_path, dsl_path, exc)
            return None

        self._log.info(
            "Rule scoring done: qid=%s score=%.2f grade=%s report=%s",
            qid,
            result.overall,
            result.grade,
            self.config.rule_report_dir_for(qid) / "report.html",
        )
        return result

    def _write_rule_batch_report(self, render_results: list[RenderResult]) -> None:
        if not self.config.enable_rule_check:
            return
        rule_results = [result.rule_result for result in render_results if result.rule_result is not None]
        if not rule_results:
            self._log.error("Rule batch report skipped because no rule scores were generated")
            return

        try:
            self._ensure_rule_module_path()
            from aesthetic_rule_check.reports import write_batch_index

            summary_path, index_path = write_batch_index(rule_results, self.config.rule_report_dir)
        except Exception as exc:
            self._log.error("Rule batch report failed: output=%s error=%s", self.config.rule_report_dir, exc)
            return

        self._log.info(
            "Rule batch report done: summary=%s index=%s report=%s",
            summary_path,
            index_path,
            self.config.rule_report_dir / "report.html",
        )

    def _load_rule_evaluator(self):
        self._ensure_rule_module_path()
        from aesthetic_rule_check import evaluate_card

        return evaluate_card

    def _ensure_rule_module_path(self) -> None:
        rule_root = self.config.project_root / "Aesthetic_Rule_Check"
        rule_root_text = str(rule_root)
        if rule_root_text not in sys.path:
            sys.path.insert(0, rule_root_text)


def qid_from_dsl_path(path: Path, safe_sn: str | None = None) -> str:
    qid = path.stem
    if safe_sn and qid.startswith(f"{safe_sn}_"):
        return qid[len(safe_sn) + 1 :]
    return qid
